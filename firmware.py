# Lockr Capstone Project
# Northeastern University 2016
import sys
import logging
from flask import Flask, jsonify, request, make_response
from flask.ext.sqlalchemy import SQLAlchemy
from datetime import datetime
import RPi.GPIO as GPIO
import time
import uuid
import redis
from celery import Celery
from celery.task import Task
from celery.registry import tasks

UID = 12345
COORDINATES = {'lat': '42.34', 'long': '-71.09'}
GPIO_LOCKER1 = 11
GPIO_LOCKER2 = 12
GPIO_LOCKER3 = 13

LOCKER_MAP = [GPIO_LOCKER1, GPIO_LOCKER2, GPIO_LOCKER3]

OPEN_TIME = 15
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LOCKER_MAP, GPIO.OUT, initial=GPIO.LOW)

app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)
app.logger.info("Firmware application started.")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///records.db'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
db = SQLAlchemy(app)

app.logger.info("Started backend engine.")

r_server = redis.Redis('localhost')
def make_celery(app):
    celery = Celery(app.import_name, broker =app.config['CELERY_BROKER_URL'], include['firmware',])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self,*args,**kwargs)
    celery.Task = ContextTask
    return celery

class Record(db.Model):
    __tablename__ = 'records'
    rental_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False)
    locker_id = db.Column(db.Integer, nullable=False)
    date_allocated = db.Column(db.DateTime, nullable=False)
    date_in = db.Column(db.DateTime, nullable=True)
    date_out = db.Column(db.DateTime, nullable=True)
    checked_out = db.Column(db.Boolean, nullable=False)
    pin = db.Column(db.Integer, nullable=True)

    @property
    def serialize(self):
        return {
            'rental_id': self.rental_id,
            'customer_id': self.customer_id,
            'locker_id': self.locker_id,
            'date_allocated': _dump_datetime(self.date_allocated),
            'date_in': _dump_datetime(self.date_in),
            'date_out': _dump_datetime(self.date_out),
            'checkout_out': self.checked_out,
            'pin': self.pin
        }
        
celery = make_celery(app)
app.logger.info("Started celery backend")

@celery.task(name='firmware._check_reservation')
def _check_reservation(customer_id):
    record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
    app.logger.info("Checked record %s.", record)
        
    if record.date_in is None:
        app.logger.info("Here we push to server")
        record.checked_out = False
        record.date_out = datetime.utcnow()
        db.session.commit()
    else:
        app.logger.info("Didn't de-allocate")
        
    return

@app.route('/get_hub_info', methods = ['GET'])
def get_hub_info():
    payload = {'uid': str(UID),
               'lat': str(COORDINATES['lat']),
               'long': str(COORDINATES['long']),
               'openUnits': str(get_num_open_lockers()),
               'totalUnits': get_num_lockers()
               }
               
    return jsonify(payload)
               
@app.route('/get_uid', methods=['GET'])
def get_uid():
    """
    Return UID of LockrHub

    :return: UID
    """
    return str(UID)


@app.route('/get_coordinates', methods=['GET'])
def get_coordinates():
    """
    Return physical location of the LockrHub

    :return: coordinates
    """
    return jsonify(COORDINATES)


@app.route('/get_num_lockers', methods=['GET'])
def get_num_lockers():
    """
    Return number of lockers (hardcoded)

    :return: int num of lockers
    """
    return str(len(LOCKER_MAP))


@app.route('/allocate_locker', methods=['POST'])
def allocate_locker():
    """
    Allocate locker to given user.

    A customer ID must be given.

    :return: response
    """
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')
    locker_id = _protected_input(json_data, 'locker_id')
    pin = _protected_input(json_data, 'pin')
    assert customer_id
    
    if locker_id is not None:
        if _is_locker_open(locker_id):
            response = _allocate_locker(customer_id, pin, locker_id)
        else:
            response = {'err': 'Locker is not available'}
    else:
        response = _allocate_locker(customer_id, pin)

    return jsonify(response)


@app.route('/start_rental', methods=['POST'])
def start_rental():
    """
    Starts rental for given customer 

    :return: rental JSON response

    """
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')
    assert customer_id

    response = _start_rental(customer_id)
    
    return jsonify(response)


@app.route('/deallocate_locker', methods=['POST'])
def deallocate_locker():
    """
    End locker rental on the given locker.

    A customer ID must be given.

    :return: response
    """
    json_data = request.get_json(force=True)

    customer_id = _protected_input(json_data, 'customer_id')
    assert customer_id

    response = _deallocate_locker(customer_id)

    return jsonify(response)


@app.route('/customer_status', methods=['GET'])
def get_customer_status():
    """
    Return complete history of rentals on this locker hub for a specific customer.

    :return: a list of record responses
    """
    customer_id = request.args.get('customer_id')
    if not customer_id:
        return {'err': 'No customer_id given.'}
    record_list = Record.query.filter_by(customer_id=customer_id).all()
    return jsonify(json_list=[i.serialize for i in record_list])


@app.route('/open_locker', methods=['POST'])
def open_locker():
    """
    Turns on the GPIO pin associated with the locker. 
    
    Requires customer_id and locker_id in json dict

    :return: Customer record 
    
    Not Yet Tested
    """
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')
    locker_id = _protected_input(json_data, 'locker_id')
    pin = _protected_input(json_data, 'pin')
    assert customer_id
    assert locker_id
    assert pin
    
    # Opens locker for set amount of time
    record = Record.query.filter_by(customer_id=customer_id, locker_id=locker_id, checked_out=True).first()
    if record:
        if record.pin != pin:
            response = {'err': 'Incorrect pin.'}
        else:
            response = record.serialize
            _open_locker(locker_id)
    else:
        response = {'err': 'No record found.'}

    return jsonify(response)


@app.route('/get_open_lockers', methods=['GET'])
def get_open_lockers():
    """
    Returns open locker ids
    
    not tested yet
    """
    open_lockers = _get_open_lockers()
    return jsonify(json_list=[i for i in open_lockers])


@app.route('/get_num_open_lockers', methods=['GET'])
def get_num_open_lockers():
    """
    Returns total number of open lockers
    """
    open_lockers = _get_open_lockers()
    num_open_lockers = len(open_lockers)
    return str(num_open_lockers)


def _allocate_locker(customer_id, pin, locker_id=None):
    """
    Private function to allocate locker to specified customer.

    Add record entry to backend.
    If locker number not provided, find an open locker.

    :param customer_id:
    :param pin:
    :param locker_id:
    :return:
    """
    if locker_id is None:
        try:
            locker_id = _get_open_lockers()[0]
        except IndexError:
            return {'err': 'There are no available lockers.'}

    new_record = Record(rental_id=int(uuid.uuid4().time_low),
                        customer_id=customer_id,
                        locker_id=locker_id,
                        checked_out=True,
                        pin=pin,
                        date_allocated=datetime.utcnow()
                        )

    db.session.add(new_record)
    db.session.commit()
    
    ImageTask._check_reservation.apply_async(args=[customer_id], countdown=1200)
    
    return new_record.serialize


def _open_locker(locker_id):
    """
    Private Open Locker Function
    
    Turns GPIO pin related to the locker_id to High for OPEN_TIME seconds
    
    :param locker_id:
    :return:
    """
    GPIO.output(locker_id, GPIO.HIGH)
    time.sleep(OPEN_TIME)
    GPIO.output(locker_id, GPIO.LOW)
    
    return


def _get_open_lockers():
    """
    Private Function to find all open lockers
    
    :return list of locker_ids:
    """
    open_lockers = []
    for locker in LOCKER_MAP:
        if _is_locker_open(locker):
            open_lockers.append(locker)
    
    return open_lockers


def _start_rental(customer_id):
    """
    Starts Rental of locker related to customer_id

    :return: record
    """
    record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
    app.logger.info("Retrieved record %s.", record)
    record.date_in = datetime.utcnow()
    db.session.commit()

    return record.serialize


def _deallocate_locker(customer_id):
    """
    End current locker rental for given customer.

    Query backend for active customer rental.
    If customer has no active rental return error.

    :param customer_id:
    :return: record
    """
    record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
    app.logger.info("Retrieved record %s.", record)
    record.checked_out = False
    record.date_out = datetime.utcnow()
    db.session.commit()
    return record.serialize
    

def _is_locker_open(locker_id):
    """
    Checks if given locker number is open.

    :param locker_id:
    :return: boolean: True if open, False if not open.
    """
    record = Record.query.filter_by(locker_id=locker_id, checked_out=True).all()
    
    if int(locker_id) not in LOCKER_MAP:
        return False
        
    if record:
        app.logger.info("Retrieved record %s.", record)
        status = False
    else:
        status = True

    return status


def _pin_unlock(user_input):
    user_input = str(user_input)
    locker_id = int(user_input[:2])
    pin = int(user_input[2:])
    
    record = Record.query.filter_by(locker_id=locker_id, checked_out=True).first()
    if record:
        app.logger.info("Retrieved record %s.", record)
        if pin == record.pin:
            _open_locker(locker_id)
            response = record
        else: 
            response = 'err'
    else:  
        response = 'err'
    
    return response


def _dump_datetime(value):
    """
    Deserialize datetime object into string form for JSON processing.

    :param value:
    :return:
    """
    if value is None:
        return None
    return [value.strftime("%Y-%m-%d"), value.strftime("%H:%M:%S")]


def _protected_input(json_data, parameter_name):
    """
    Return string if parameter_name exists within json_data
    Otherwise return None.

    :param parameter_name:
    :return:
    """
    try:
        value = json_data[parameter_name]
    except KeyError:
        value = None
    return str(value)


if __name__ == '__main__':
    try:
        db.create_all()
        app.run(host='0.0.0.0', debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
