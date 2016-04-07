SRCFILES=$(wildcard *.py)

default: all
all: redis run

redis:
	sudo apt-get -y install redis-server
	redis-server --daemonize yes

run: $(SRCFILES)
	sudo apt-get -y install python-dev
	pip install --upgrade pip && pip install -r requirements.txt
	python firmware.py

clean:
	find . -name '*.pyc' -exec rm -f {} +
