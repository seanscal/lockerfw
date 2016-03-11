# Lockr Capstone Project
# Northeastern University 2016
import sys
import logging
from flask import Flask, jsonify, request, make_response
from flask.ext.sqlalchemy import SQLAlchemy
from datetime import datetime
import RPI.GPIO as GPIO
import time

UID = 12345
COORDINATES = (42.34, -71.09)
GPIO_LOCKER1 = 11
GPIO_LOCKER2 = 12
GPIO_LOCKER3 = 13

Open_time = 15
GPIO.setmode(GPIO.BOARD)
lockers = [GPIO_LOCKER1,GPIO_LOCKER2,GPIO_LOCKER3]
GPIO.setup(lockers, GPIO.OUT, initial=GPIO.LOW)

app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)
app.logger.info("Firmware application started.")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///records.db'
db = SQLAlchemy(app)

app.logger.info("Started backend engine.")

class Record(db.Model):
    __tablename__ = 'records'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False)
    locker_id = db.Column(db.Integer, nullable=False)
    date_in = db.Column(db.DateTime, nullable=True)
    date_out = db.Column(db.DateTime, nullable=True)
    checked_out = db.Column(db.Boolean, nullable=False)
    pin = db.Column(db.Integer, nullable=False)

    @property
    def serialize(self):
        return {
            'customer_id': self.customer_id,
            'locker_id': self.locker_id,
            'date_in': dump_datetime(self.date_in),
            'date_out': dump_datetime(self.date_out),
            'checkout_out': self.checked_out
            'pin' : self.pin
        }


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
    return str(COORDINATES)


@app.route('/allocate_locker', methods=['POST'])
def allocate_locker():
    """
    Allocate locker to given user.

    A customer ID and locker ID must be given.

    TODO (If locker number not specified, auto select an open locker.
    If no lockers are available, return error.)

    :return: response
    """
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')
    locker_id = _protected_input(json_data, 'locker_id')
    pin = _protected_input(json_data, 'pin')
    assert customer_id
    
    if locker_id:
        if _is_locker_open(locker_id):
            response = _allocate_locker(customer_id, pin, locker_id)
        else:
            response = "err"
    else:
        response = _allocate_locker(customer_id, pin)

    return jsonify(response)
  
@app.route('/start_retnal', methods=['POST'])  
def start_rental():
    json_data = request.get_json(force=True)
    customer_id = _protected_input(json_data, 'customer_id')

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
    json_data = request.get_json(force=True)
    customer_id = json_data['customer_id']
    record_list = Record.query.filter_by(customer_id=customer_id).all()
    return jsonify(json_list=[i.serialize for i in record_list])

@app.route('/open_locker',methods=['POST'])
def open_locker():
    json_data = request.get_json(force=True)
    locker_id = _protected_input(json_data, 'locker_id')
    
    #Opens locker for set amount of time
    if _is_locker_open(locker_id):
        response = Record.query.filter_by(locker_id=locker_id, checked_out=True).first()
        GPIO.output(locker_id, GPIO.HIGH)
        time.sleep(Open_time)
        GPIO.output(locker_id,GPIO.LOW)
    else:
        response = 'err'
    
    return response
    
@app.route('/find_open_lockers', methods = ['GET'])
"""
Returns open locker ids

not tested yet
"""
def find_open_lockers():
    open_lockers = _open_lockers()
    return jsonify(json_list=[i for i in open_locker])

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
        locker_id = _open_lockers()[0]

    new_record = Record(customer_id=customer_id,
                        locker_id=locker_id,
                        checked_out=True,
                        pin = pin
                        )

    db.session.add(new_record)
    db.session.commit()

    return new_record.serialize

def _open_lockers():
    """
    Finds all open lockers
    
    :return locker_id:
    """
    open_lockers = []
    for locker in lockers:
        if _is_locker_open(locker):
            open_lockers.append(locker)
    
    return open_lockers

def _start_rental(customer_id):
    """
    Starts Rental of locker related to customer_id
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
    :return:
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

    if record:
        app.logger.info("Retrieved record %s.", record)
        status = False
    else:
        status = True

    return status


def dump_datetime(value):
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


@app.route('/test', methods=['GET'])
def test_get():
    return "Hello World!"


@app.route('/test2', methods=['POST'])
def test_post():
    json_data = request.get_json(force=True)
    app.logger.debug("JSON=%s", json_data)
    return jsonify(json_data)


if __name__ == '__main__':
    try:
        db.create_all()
        app.run(host='0.0.0.0', debug=True)
    except KeyboardInterrupt:
        GPIO.cleanup()

