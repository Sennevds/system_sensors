#!/usr/bin/env python3
from subprocess import check_output
from re import findall
import psutil
import sys
import os
import threading, time, signal
from datetime import timedelta
import datetime as dt
import paho.mqtt.client as mqtt
import pytz
import yaml
import apt
from pytz import timezone
import argparse

UTC = pytz.utc
DEFAULT_TIME_ZONE = None

mqttClient = None
SYSFILE = "/sys/devices/platform/soc/soc:firmware/get_throttled"
WAIT_TIME_SECONDS = 60
deviceName = None
class ProgramKilled(Exception):
    pass


def signal_handler(signum, frame):
    raise ProgramKilled


class Job(threading.Thread):
    def __init__(self, interval, execute, *args, **kwargs):
        threading.Thread.__init__(self)
        self.daemon = False
        self.stopped = threading.Event()
        self.interval = interval
        self.execute = execute
        self.args = args
        self.kwargs = kwargs

    def stop(self):
        self.stopped.set()
        self.join()

    def run(self):
        while not self.stopped.wait(self.interval.total_seconds()):
            self.execute(*self.args, **self.kwargs)


def utc_from_timestamp(timestamp: float) -> dt.datetime:
    """Return a UTC time from a timestamp."""
    return UTC.localize(dt.datetime.utcfromtimestamp(timestamp))


def as_local(dattim: dt.datetime) -> dt.datetime:
    """Convert a UTC datetime object to local time zone."""
    if dattim.tzinfo == DEFAULT_TIME_ZONE:
        return dattim
    if dattim.tzinfo is None:
        dattim = UTC.localize(dattim)

    return dattim.astimezone(DEFAULT_TIME_ZONE)


def get_last_boot():
    return str(as_local(utc_from_timestamp(psutil.boot_time())).isoformat())


def updateSensors():
    payload_str=('{"temperature": '
    + get_temp()
    + ', "disk_use": '
    + get_disk_usage()
    + ', "memory_use": '
    + get_memory_usage()
    + ', "cpu_usage": '
    + get_cpu_usage()
    + ', "swap_usage": '
    + get_swap_usage()
    + ', "power_status": "'
    + get_rpi_power_status()
    + '", "last_boot": "'
    + get_last_boot()
    + '", "updates": "'
    + get_updates()
    + '", "last_message": "'
    + time.ctime())
    if "check_wifi_strength" in settings and settings["check_wifi_strength"]:
        payload_str = payload_str + '", "wifi_strength": "' + get_wifi_strength()
    
    payload_str = payload_str + '"}'
    mqttClient.publish(
        topic="system-sensors/sensor/" + deviceName + "/state",
        payload=payload_str,
        qos=1,
        retain=False,
    )

def get_updates():
    cache=apt.Cache()
    cache.open(None)
    cache.upgrade()
    return str(cache.get_changes().__len__())

def get_temp():
    temp = check_output(["vcgencmd", "measure_temp"]).decode("UTF-8")
    return str(findall("\d+\.\d+", temp)[0])


def get_disk_usage():
    return str(psutil.disk_usage("/").percent)


def get_memory_usage():
    return str(psutil.virtual_memory().percent)


def get_cpu_usage():
    return str(psutil.cpu_percent(interval=None))


def get_swap_usage():
    return str(psutil.swap_memory().percent)

def get_wifi_strength():#check_output(["/proc/net/wireless", "grep wlan0"])
     return check_output(['bash', '-c', "cat /proc/net/wireless | grep wlan0: | awk '{print int($4)}'"]).decode('utf-8').rstrip()

def get_rpi_power_status():
    _throttled = open(SYSFILE, "r").read()[:-1]
    _throttled = _throttled[:4]

    if "power_integer_state" in settings and settings["power_integer_state"]:
        return _throttled
    else:
        if _throttled == "0":
            return "Everything is working as intended"
        elif _throttled == "1000":
            return "Under-voltage was detected, consider getting a uninterruptible power supply for your Raspberry Pi."
        elif _throttled == "2000":
            return "Your Raspberry Pi is limited due to a bad powersupply, replace the power supply cable or power supply itself."
        elif _throttled == "3000":
            return "Your Raspberry Pi is limited due to a bad powersupply, replace the power supply cable or power supply itself."
        elif _throttled == "4000":
            return "The Raspberry Pi is throttled due to a bad power supply this can lead to corruption and instability, please replace your changer and cables."
        elif _throttled == "5000":
            return "The Raspberry Pi is throttled due to a bad power supply this can lead to corruption and instability, please replace your changer and cables."
        elif _throttled == "8000":
            return "Your Raspberry Pi is overheating, consider getting a fan or heat sinks."
        else:
            return "There is a problem with your power supply or system."

def check_settings(settings):
    if "mqtt" not in settings:
        print("Mqtt not defined in settings.yaml! Please check the documentation")
        sys.stdout.flush()
        sys.exit()
    if "hostname" not in settings["mqtt"]:
        print("Hostname not defined in settings.yaml! Please check the documentation")
        sys.stdout.flush()
        sys.exit()
    if "timezone" not in settings:
        print("Timezone not defined in settings.yaml! Please check the documentation")
        sys.stdout.flush()
        sys.exit()
    if "deviceName" not in settings:
        print("deviceName not defined in settings.yaml! Please check the documentation")
        sys.stdout.flush()
        sys.exit()
    if "client_id" not in settings:
        print("client_id not defined in settings.yaml! Please check the documentation")
        sys.stdout.flush()
        sys.exit()

def _parser():
    """Generate argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument("settings", help="path to the settings file")
    return parser

if __name__ == "__main__":
    args = _parser().parse_args()
    with open(args.settings) as f:
        # use safe_load instead load
        settings = yaml.safe_load(f)
    check_settings(settings)
    DEFAULT_TIME_ZONE = timezone(settings["timezone"])
    if "update_interval" in settings:
        WAIT_TIME_SECONDS = settings["update_interval"]
    mqttClient = mqtt.Client(client_id=settings["client_id"])
    deviceName = settings["deviceName"]
    if "user" in settings["mqtt"]:
        mqttClient.username_pw_set(
            settings["mqtt"]["user"], settings["mqtt"]["password"]
        )  # Username and pass if configured otherwise you should comment out this
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    if "port" in settings["mqtt"]:
        mqttClient.connect(settings["mqtt"]["hostname"], settings["mqtt"]["port"])
    else:
        mqttClient.connect(settings["mqtt"]["hostname"], 1883)
    mqttClient.publish(
        topic="homeassistant/sensor/" + deviceName + "/" + deviceName + "Temp/config",
        payload='{"device_class":"temperature","name":"'
        + deviceName
        + 'Temperature","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","unit_of_measurement":"°C","value_template":"{{ value_json.temperature}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_temperature","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:thermometer"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "DiskUse/config",
        payload='{"name":"'
        + deviceName
        + 'DiskUse","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","unit_of_measurement":"%","value_template":"{{ value_json.disk_use}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_disk_use","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:microsd"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "MemoryUse/config",
        payload='{"name":"'
        + deviceName
        + 'MemoryUse","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","unit_of_measurement":"%","value_template":"{{ value_json.memory_use}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_memory_use","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:memory"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "CpuUsage/config",
        payload='{"name":"'
        + deviceName
        + 'CpuUsage","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","unit_of_measurement":"%","value_template":"{{ value_json.cpu_usage}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_cpu_usage","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:memory"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "SwapUsage/config",
        payload='{"name":"'
        + deviceName
        + 'SwapUsage","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","unit_of_measurement":"%","value_template":"{{ value_json.swap_usage}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_swap_usage","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:harddisk"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "PowerStatus/config",
        payload='{"name":"'
        + deviceName
        + 'PowerStatus","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","value_template":"{{ value_json.power_status}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_power_status","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:power-plug"}',
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "LastBoot/config",
        payload='{"device_class":"timestamp","name":"'
        + deviceName
        + 'LastBoot","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","value_template":"{{ value_json.last_boot}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_last_boot","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:clock"}',
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic="homeassistant/sensor/"
        + deviceName
        + "/"
        + deviceName
        + "Updates/config",
        payload='{"name":"'
        + deviceName
        + 'Updates","state_topic":"system-sensors/sensor/'
        + deviceName
        + '/state","value_template":"{{ value_json.updates}}","unique_id":"'
        + deviceName.lower()
        + '_sensor_updates","device":{"identifiers":["'
        + deviceName.lower()
        + '_sensor"],"name":"'
        + deviceName
        + 'Sensors","model":"RPI '
        + deviceName
        + '","manufacturer":"RPI"}, "icon":"mdi:cellphone-arrow-down"}',
        qos=1,
        retain=True,
    )

    if "check_wifi_strength" in settings and settings["check_wifi_strength"]:
        mqttClient.publish(
            topic="homeassistant/sensor/"
            + deviceName
            + "/"
            + deviceName
            + "WifiStrength/config",
            payload='{"device_class":"signal_strength","name":"'
            + deviceName
            + 'WifiStrength","state_topic":"system-sensors/sensor/'
            + deviceName
            + '/state","unit_of_measurement":"dBm","value_template":"{{ value_json.wifi_strength}}","unique_id":"'
            + deviceName.lower()
            + '_sensor_wifi_strength","device":{"identifiers":["'
            + deviceName.lower()
            + '_sensor"],"name":"'
            + deviceName
            + 'Sensors","model":"RPI '
            + deviceName
            + '","manufacturer":"RPI"}}',
            qos=1,
            retain=True,
        )
    job = Job(interval=timedelta(seconds=WAIT_TIME_SECONDS), execute=updateSensors)
    job.start()
    mqttClient.loop_forever()

    while True:
        try:
            time.sleep(1)
        except ProgramKilled:
            print("Program killed: running cleanup code")
            sys.stdout.flush()
            job.stop()
            break

