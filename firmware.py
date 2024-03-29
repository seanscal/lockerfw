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
import requests
import json
import time

UID = 12345
COORDINATES = {'lat': '42.34', 'long': '-71.09'}
GPIO_LOCKER1 = 16
GPIO_LOCKER2 = None
GPIO_LOCKER3 = None
BUTTON_PIN_LOCKER1 = 18

LOCKER_MAP = [GPIO_LOCKER1]
BUTTON_PINS = [BUTTON_PIN_LOCKER1]
BUTTON_MAP = {str(GPIO_LOCKER1): BUTTON_PIN_LOCKER1}

OPEN_TIME = 15
GPIO.setmode(GPIO.BOARD)
GPIO.setup(LOCKER_MAP, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(BUTTON_PINS, GPIO.IN, pull_up_down = GPIO.PUD_UP)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///records.db'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
db = SQLAlchemy(app)

def make_celery(app):
    celery = Celery(app.import_name, broker =app.config['CELERY_BROKER_URL'])
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
            'hub_id': UID,
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
    if record is None:
        app.logger.info("Locker Already de-allocated: ending")
        return
    if record.date_in is None:
        app.logger.info("Here we push to server")
        req_data = {'customer_id' : str(customer_id)}
        try:
            response = requests.post('http://localhost:5000/deallocate_locker', data=json.dumps(req_data))
            try:
                requests.post('http://nulockerhub.com/api/pi/reservationExpired', data=json.dumps(response.serialize))
            except:
                app.logger.exception("Reservation expiration request to server failed.")
        except:
            app.logger.exception("Deallocation failed.")
    else:
        app.logger.info("Didn't de-allocate")


        
    return


@app.route('/get_hub_info', methods=['GET'])
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
    start = _protected_input(json_data, 'start_rental')

    if not customer_id:
        response = {'err': 'Must provide customer id in order to allocate locker'}
        app.logger.error("Error in allocate_locker: %s", response['err'])
        return jsonify(response)

    if not pin:
        response = {'err': 'Must provide pin in order to allocate locker'}
        app.logger.error("Error in allocate_locker: %s", response['err'])
        return jsonify(response)

    if not locker_id:
        try:
            locker_id = _get_open_lockers()[0]
        except IndexError:
            response = {'err': 'There are no available lockers.'}
            app.logger.error("Error in allocate_locker: %s", response['err'])
            return jsonify(response)
    else:
        if not _is_locker_open(locker_id):
            response = {'err': 'Locker %s is not available' % locker_id}
            app.logger.error("Error in allocate_locker: %s", response['err'])
            return jsonify(response)

    record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
    if record:
        response = {'err': 'Customer %s already has locker checked out, not allocating' % customer_id}
        app.logger.error("Error in allocate_locker: %s", response['err'])
        return jsonify(response)

    app.logger.info("Allocating locker &s for customer id %s", locker_id, customer_id)
    
    response = _allocate_locker(customer_id, pin, locker_id)

    if start == '1':
        response = _start_rental(customer_id)

    return jsonify(response)


@app.route('/start_rental', methods=['POST'])
def start_rental():
    """
    Starts rental for given customer 

    :return: rental JSON response

    """
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')
    if not customer_id:
        response = {'err': 'Must provide customer id in order to start rental'}
        app.logger.error("Error in start_rental: %s", response['err'])
        return jsonify(response)

    response = _start_rental(customer_id)

    record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
    _open_locker.apply_async(args=[record.locker_id])

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

    if not customer_id:
        response = {'err': 'Must provide customer id in order to deallocate'}
        app.logger.error("Error in deallocate_locker: %s", response['err'])
        return jsonify(response)

    response = _deallocate_locker(customer_id)
    app.logger.info("Deallocate locker for customer %s", customer_id)

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
    locker_id = _protected_input(json_data, 'locker_id')
    pin = int(_protected_input(json_data, 'pin'))

    if not locker_id:
        response = {'err': 'Must provide locker id in order to open locker'}
        app.logger.error("Error in open_locker: %s", response['err'])
        return jsonify(response)

    if not pin:
        response = {'err': 'Must provide pin in order to open locker'}
        app.logger.error("Error in open_locker: %s", response['err'])
        return jsonify(response)

    # Opens locker for set amount of time
    record = Record.query.filter_by(locker_id=locker_id, checked_out=True).first()
    if record:
        if record.pin != pin:
            response = {'err': 'Incorrect pin.'}
            app.logger.error("Error in open_locker: %s", response['err'])
        else:
            response = record.serialize
            _open_locker.apply_async(args=[locker_id])
            response['TimeOpened'] = _dump_datetime(datetime.utcnow())
    else:
        response = {'err': 'No record found.'}

    return jsonify(response)


@app.route('/get_open_lockers', methods=['GET'])
def get_open_lockers():
    """
    Returns open locker ids
    """
    open_lockers = _get_open_lockers()
    return jsonify(json_list=[i for i in open_lockers])


@app.route('/get_customers', methods=['GET'])
def get_customers():
    """
    Return customer ids with open reservations
    """
    customers = _get_customers()
    return jsonify(json_list=[i for i in customers])


@app.route('/get_num_open_lockers', methods=['GET'])
def get_num_open_lockers():
    """
    Returns total number of open lockers
    """
    open_lockers = _get_open_lockers()
    num_open_lockers = len(open_lockers)
    return str(num_open_lockers)


@app.route('/locker_door_open', methods=['GET'])
def locker_door_open():
    locker_id = request.args.get('locker_id')
    if not locker_id:
        response = {'err': 'Must provide locker id'}
        return jsonify(response)
    isOpen = _locker_door_open(locker_id)
    return isOpen


def _locker_door_open(locker_id):
    counter = 0
    for t in xrange(5):
        if not GPIO.input(BUTTON_MAP[locker_id]):
            counter += 1
    if counter > 3:
        return 'True'
    else:
        return 'False'
    

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
    new_record = Record(rental_id=int(uuid.uuid4().time_low),
                        customer_id=customer_id,
                        locker_id=locker_id,
                        checked_out=True,
                        pin=pin,
                        date_allocated=datetime.utcnow()
                        )
    
    db.session.add(new_record)
    db.session.commit()
        
    _check_reservation.apply_async(args=[customer_id], countdown=30)
        
    response = new_record.serialize
    return response 


@celery.task(name='firmware._open_locker')
def _open_locker(locker_id):
    """
    Private Open Locker Function
    
    Turns GPIO pin related to the locker_id to High for OPEN_TIME seconds
    
    :param locker_id:
    :return:
    """
    locker_id = int(locker_id)
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


def _get_customers():
    """
    Private Function to find customers with open rentals
    
    :return list of customer_ids:
    """
    records = Record.query.filter_by(checked_out=True).all()
    customers = []
    for record in records:
        rental = {'customer_id': record.customer_id, 'locker_id': record.locker_id}
        customers.append(rental)
    return customers


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
    try:
        record = Record.query.filter_by(customer_id=customer_id, checked_out=True).first()
        app.logger.info("Retrieved record %s.", record)
        record.checked_out = False
        record.date_out = datetime.utcnow()
        db.session.commit()
        response = record.serialize
    except AttributeError:
        response = {'err': 'No checked-out locker found for customer %s' % customer_id}
        app.logger.error("Error in deallocate_locker: %s", response['err'])

    return response
    

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

"""
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
"""


def _dump_datetime(value):
    """
    Deserialize datetime object into string form for JSON processing.

    :param value:
    :return:
    """
    if value is None:
        return None
    return time.mktime(value.timetuple())


def _protected_input(json_data, parameter_name):
    """
    Return string if parameter_name exists within json_data
    Otherwise return None.

    :param parameter_name:
    :return:
    """
    try:
        value = str(json_data[parameter_name])
    except KeyError:
        value = None
    return value


if __name__ == '__main__':
    try:
        app.logger.addHandler(logging.StreamHandler(sys.stdout))
        file_handler = logging.handlers.RotatingFileHandler('/var/log/nu_lockr.log', maxBytes=1000000)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.DEBUG)
        app.logger.info("Firmware application started.")

        app.logger.info("Started backend engine.")
        r_server = redis.Redis('localhost')
        
        db.create_all()
        app.run(host='0.0.0.0', debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()
    except Exception as e:
        app.logger.exception("Unhandled exception: %s", e.message)
        sys.exit(-1)
