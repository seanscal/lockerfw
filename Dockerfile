FROM debian:wheezy
WORKDIR /code/

RUN apt-get update &&  \
    apt-get install -qy python-dev python-pip git libffi-dev libssl-dev

ADD ./ /code/
RUN pip install -r requirements.txt

RUN useradd -d /home/user -m -s /bin/bash user
RUN chown -R user:user /code/
USER user