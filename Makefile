SRCFILES=$(wildcard *.py)

default: all
all: run

run: $(SRCFILES)
	/home/pi/redis-stable/src/redis-server --daemonize yes
	sudo apt-get install python-dev
	pip install --upgrade pip && pip install -r requirements.txt
	python firmware.py

clean:
	find . -name '*.pyc' -exec rm -f {} +
