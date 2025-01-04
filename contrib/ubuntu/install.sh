#!/bin/bash
set -e

USER=$1
HOST=$2
read -s -p "MQTT Password: " PASS
echo
DEVICENAME=$(hostname)
TIMEZONE=$(timedatectl |grep "Time zone"|awk '{print $3}')

echo "update and install dependencies"
apt update
apt install -y curl python3 python3-pip python3-dev python3-apt python3-venv

echo "Create group and user systemsensors"
useradd --system --no-create-home --shell=/sbin/nologin systemsensors

echo "Creating venv"
mkdir -p  /opt/systemsensors/
python3 -m venv --system-site-packages /opt/systemsensors/venv
source /opt/systemsensors/venv/bin/activate

echo "Install pip requirements"
curl -o /tmp/requirements.txt https://raw.githubusercontent.com/Sennevds/system_sensors/master/requirements.txt
pip3 install -r /tmp/requirements.txt

echo "Install system_sensors"
mkdir -p  /opt/systemsensors/
curl -o /opt/systemsensors/sensors.py https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/sensors.py
curl -o /opt/systemsensors/system_sensors.py  https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/system_sensors.py

echo "mqtt:
  hostname: $HOST
  port: 1883 #defaults to 1883
  user: $USER
  password: $PASS
deviceName: $DEVICENAME
client_id: $DEVICENAME
timezone: $TIMEZONE
update_interval: 60 #Defaults to 60
sensors:
  temperature: true
  clock_speed: true
  disk_use: true
  memory_use: true
  cpu_usage: true
  load_1m: true
  load_5m: true
  load_15m: true
  net_tx: true
  net_rx: true
  swap_usage: true
  power_status: true
  last_boot: false
  hostname: false
  host_ip: false
  host_os: false
  host_arch: false
  last_message: false
  updates: true
  wifi_strength: false
  wifi_ssid: false
  external_drives:
    # Only add mounted drives here, e.g.:
    # Drive1: /media/storage" > /opt/systemsensors/settings.yaml

chmod 770 -R /opt/systemsensors
chown -R systemsensors:systemsensors /opt/systemsensors

echo "[Unit]
Description=System Sensor service
After=multi-user.target

[Service]
User=systemsensors
Type=idle
ExecStart=/opt/systemsensors/venv/bin/python3 /opt/systemsensors/system_sensors.py /opt/systemsensors/settings.yaml

[Install]
WantedBy=multi-user.target" > /etc/systemd/system/system_sensors.service

systemctl daemon-reload
systemctl enable system_sensors
systemctl start system_sensors

echo "Done, see the status with 'systemctl status system_sensors'"