#!/bin/sh
# for proxmox7
# version without check
# Autodetect host timezone
# disable wifi
# t.me / proxmox-ha
USER=$1
PASS=$2
HOST=$3
DEVICENAME=$4
TIMEZONE=$(timedatectl |grep "Time zone"|awk '{print $3}')

echo "update apt-get and install"
apt-get update
apt-get install -y git lm-sensors python3 python3-pip curl python3-apt




echo "Create group and user systemsensors "
groupadd systemsensors
useradd systemsensors -r -g systemsensors

echo "Install pip requirements"

curl -o /tmp/requirements.txt https://raw.githubusercontent.com/Sennevds/system_sensors/master/requirements.txt
pip3 install -r /tmp/requirements.txt

mkdir -p  /home/systemsensors/etc/ /home/systemsensors/bin/

curl -o /home/systemsensors/bin/sensors.py https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/sensors.py
curl -o /home/systemsensors/bin/system_sensors.py  https://raw.githubusercontent.com/Sennevds/system_sensors/master/src/system_sensors.py

chmod 755 /home/systemsensors/bin/sensors.py /home/systemsensors/bin/system_sensors.py
chown -R systemsensors:systemsensors /home/systemsensors/


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
  hostname: true
  host_ip: true
  host_os: true
  host_arch: true
  last_message: false
  updates: true
  wifi_strength: false
  wifi_ssid: false
  external_drives:
    # Only add mounted drives here, e.g.:
    # Drive1: /media/storage" > /home/systemsensors/etc/settings.yaml




echo "[Unit]
Description=System Sensor service
After=multi-user.target

[Service]
User=systemsensors
Type=idle
ExecStart=/usr/bin/python3 /home/systemsensors/bin/system_sensors.py /home/systemsensors/etc/settings.yaml

[Install]
WantedBy=multi-user.target" > /etc/systemd/system/system_sensors.service

systemctl daemon-reload
systemctl enable system_sensors
systemctl start system_sensors
systemctl status system_sensors

