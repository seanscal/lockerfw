import requests
import json

while 1:
    locker_id = input('locker id: ')
    pin = input('pin: ')
    req_data = {'locker_id': str(locker_id), 'pin': str(pin)}
    r = requests.post('http://localhost:5000/open_locker', data=json.dumps(req_data))
    if r.status_code != requests.codes.ok:
        pass
