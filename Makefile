SRCFILES=$(wildcard *.py)
BUILD_DIR=build
BUILD_FILES=$(BUILD_DIR)/Dockerfile $(BUILD_DIR)/requirements.txt

default: all
all: rpi
build_rpi: build/rpi/.build.created
build_sim: build/simulated/.build.created

rpi: $(SRCFILES) build_rpi
	docker run --rm -P\
	-u user \
	-v `pwd`/firmware:/code/firmware \
	-e PYTHONPATH=/code \
	--name lockr-firmware-rpi \
	lukema/lockr-rpi-builder python firmware/firmware.py

sim: $(SRCFILES) build_sim
	docker run --rm -P\
	-u user \
	-v `pwd`/firmware:/code/firmware \
	-e PYTHONPATH=/code \
	--name lockr-firmware-sim \
	lukema/lockr-sim-builder python firmware/firmware.py

build/rpi/.build.created:
	cd build/rpi && docker build -t lukema/lockr-rpi-builder .
	touch build/rpi/.build.created

this:
	docker build -t lukema/lockr-builder .
	docker run --rm -P -u user -v `pwd`:/code/ --name lockr-fw lukema/lockr-builder

clean:
	find . -name '*.created' -exec rm -f {} +
	find . -name '*.pyc' -exec rm -f {} +
	-docker rmi lukema/lockr-rpi-builder
	-docker rmi lukema/lockr-sim-builder
	-docker rm -f lockr*
