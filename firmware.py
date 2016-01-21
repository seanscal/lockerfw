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
def test_get():
    return "Hello World!"

@app.route('/test2', methods=['POST'])
def test_post():
    json_data = request.get_json(force=True)
    app.logger.debug("JSON=%s", json_data)
    return jsonify(json_data)

if __name__ == '__main__':
    app.run(debug=True)


