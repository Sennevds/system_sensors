FROM arm32v7/python:latest

ENV TZ Europe/Berlin
ENV MQTT_HOST localhost
ENV MQTT_PORT 1883
ENV DEVICE_NAME pi
ENV WAIT_TIME 60

COPY src/system_sensors.py requirements.txt /

RUN pip install -r requirements.txt

CMD [ "python", "./system_sensors.py" ]
