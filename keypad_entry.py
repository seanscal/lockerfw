import requests
import json

while 1:
    locker_id = input('locker id: ')
    pin = input('pin: ')
    req_data = {'locker_id': locker_id, 'pin': pin}
    r = requests.post('0.0.0.0:5000', data=json.dumps(req_data))
    if r.status_code != requests.codes.ok:
        pass
