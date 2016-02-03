# Lockr Capstone Project
# Northeastern University 2016
import sys
import logging
import models
from flask import Flask, jsonify, request, make_response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime


UID = 12345
COORDINATES = (42.34, -71.09)
GPIO_LOCKER1 = 11
GPIO_LOCKER2 = 12
GPIO_LOCKER3 = 13


app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)
app.logger.info("Firmware application started.")

@app.route('/init')
def intialize_backend():
    """
    Initialize SQLite database

    :return:
    """
    global engine
    engine = create_engine('sqlite:///records.db', echo=True)


@app.route('/get_uid')
def get_uid():
    """
    Return UID of LockrHub

    :return: UID
    """
    return UID


@app.route('/allocate_locker')
def allocate_locker():
    """
    Allocate locker to given user.

    If locker number not specified, auto select an open locker.
    If no lockers are specified, return error.
    Otherwise, return the corresponding locker number.

    :return: response
    """
    json_data = request.get_json(force=True)
    customer_id = json_data['customer_id']
    locker_id = json_data['locker_id']
    assert customer_id

    if json_data[locker_id]:
        if not _is_locker_open(locker_id):
            response = "err"
        response = _allocate_locker(customer_id, locker_id)
    else:
        response = _allocate_locker(customer_id)

    return response


@app.route('deallocate_locker')
def deallocate_locker():
    """
    Deallocate locker of the given user.

    :return: 1 if successful, 0 if unsuccessful, -1 if error
    """
    json_data = request.get_json(force=True)
    customer_id = json_data['customer_id']
    assert customer_id

    response = _deallocate_locker(customer_id)

    return response


def _allocate_locker(customer_id, locker_id=None):
    """
    Private function to allocate locker to specified customer.

    Add record entry to backend.
    If locker number not provided, find an open locker.

    :param customer_id:
    :param locker_id:
    :return:
    """
    Session = sessionmaker(bind=engine)
    session = Session()

    new_record = models.Record(customer_id=customer_id,
                               locker_id=locker_id,
                               date_in=datetime,
                               checked_out=True
                               )

    session.add(new_record)
    session.commit()



def _deallocate_locker(customer_id):
    """
    End current locker rental for given customer.

    Query backend for active customer rental.
    If customer has no active rental return error.

    :param customer_id:
    :return:
    """
    Session = sessionmaker(bind=engine)
    session = Session()

    record = session.query(models.Record).filter_by(customer_id=customer_id)
    app.logger.info("Retrieved record %s.", record)

    record.checked_out = False
    record.date_out = datetime


def _is_locker_open(locker_id):
    """
    Checks if given locker number is open.

    :param locker_id:
    :return: boolean: True if open, False if not open.
    """
    Session = sessionmaker(bind=engine)
    session = Session()

    record = session.query(models.Record).filter_by(locker_id=locker_id)
    app.logger.info("Retrieved record %s.", record)

    return record.checked_out


@app.route('/test', methods=['GET'])
def test_get():
    return "Hello World!"

@app.route('/test2', methods=['POST'])
def test_post():
    json_data = request.get_json(force=True)
    app.logger.debug("JSON=%s", json_data)
    return jsonify(json_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)


