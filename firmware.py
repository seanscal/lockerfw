# Lockr Capstone Project
# Northeastern University 2016
import sys
import logging
from flask import Flask, jsonify, request, make_response


app = Flask(__name__)
app.logger.addHandler(logging.StreamHandler(sys.stdout))
app.logger.setLevel(logging.DEBUG)
app.logger.info("Firmware application started.")

@app.route('/test', methods=['GET'])
def test():
    pass

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

if __name__ == '__main__':
    app.run(debug=True)


