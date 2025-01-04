#!/bin/bash
set -e

echo "Stopping system_sensors"
systemctl stop system_sensors

echo "Update and install any new dependencies"
apt update
apt install -y curl python3 python3-pip python3-dev python3-apt

echo "Activating venv"
source /opt/systemsensors/venv/bin/activate

echo "Install any new pip requirements"
curl -o /tmp/requirements.txt https://raw.githubusercontent.com/Sennevds/system_sensors/master/requirements.txt
pip3 install -r /tmp/requirements.txt

echo "Updating system_sensors"
curl -o /opt/systemsensors/sensors.py https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/sensors.py
curl -o /opt/systemsensors/system_sensors.py  https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/system_sensors.py

chmod 770 -R /opt/systemsensors
chown -R systemsensors:systemsensors /opt/systemsensors

echo "Starting system_sensors"
systemctl start system_sensors

echo "Done, see the status with 'systemctl status system_sensors'"
