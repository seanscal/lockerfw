SRCFILES=$(wildcard *.py)

default: all
all: run

run: $(SRCFILES)
	pip install -r requirements.txt
	python firmware.py

clean:
	find . -name '*.pyc' -exec rm -f {} +
