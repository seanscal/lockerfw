import requests
import json

while 1:
    try:
        locker_id = input('locker id: ')
        pin = input('pin: ')
        req_data = {'locker_id': str(locker_id), 'pin': str(pin)}
    except (KeyboardInterrupt, SystemExit):
        break
    except:
        pass
    else:
        try:
            r = requests.post('http://localhost:5000/open_locker', data=json.dumps(req_data))
        except:
            pass
        if r.status_code != requests.codes.ok:
            pass
