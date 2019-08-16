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
from pytz import timezone



UTC = pytz.utc
DEFAULT_TIME_ZONE = timezone('Europe/Brussels')#Local Time zone
broker_url = ""#MQTT server IP
broker_port = 1883 #MQTT server port
client = mqtt.Client()
#client.username_pw_set("", "") #Username and pass if configured otherwise you should comment out this
deviceName = "" #Name of your PI
SYSFILE = '/sys/devices/platform/soc/soc:firmware/get_throttled'
WAIT_TIME_SECONDS = 60

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
   client.publish(topic="system-sensors/sensor/"+ deviceName +"/state", payload='{"temperature": '+ get_temp() +', "disk_use": '+ get_disk_usage() + ', "memory_use": '+ get_memory_usage() +', "cpu_usage": '+ get_cpu_usage() +', "swap_usage": '+ get_swap_usage() +', "power_status": "'+ get_rpi_power_status() +'", "last_boot": "'+ get_last_boot() +'"}', qos=1, retain=False)

def get_temp():
    temp = check_output(["vcgencmd","measure_temp"]).decode("UTF-8")
    return str(findall("\d+\.\d+",temp)[0])

def get_disk_usage():
    return str(psutil.disk_usage('/').percent)

def get_memory_usage():
    return str(psutil.virtual_memory().percent)

def get_cpu_usage():
    return str(psutil.cpu_percent(interval=None))

def get_swap_usage():
    return str(psutil.swap_memory().percent)

def get_rpi_power_status():
    _throttled = open(SYSFILE, 'r').read()[:-1]
    _throttled = _throttled[:4]
    if _throttled == '0':
        return 'Everything is working as intended'
    elif _throttled == '1000':
        return 'Under-voltage was detected, consider getting a uninterruptible power supply for your Raspberry Pi.'
    elif _throttled == '2000':
        return 'Your Raspberry Pi is limited due to a bad powersupply, replace the power supply cable or power supply itself.'
    elif _throttled == '3000':
        return 'Your Raspberry Pi is limited due to a bad powersupply, replace the power supply cable or power supply itself.'
    elif _throttled == '4000':
        return 'The Raspberry Pi is throttled due to a bad power supply this can lead to corruption and instability, please replace your changer and cables.'
    elif _throttled == '5000':
        return 'The Raspberry Pi is throttled due to a bad power supply this can lead to corruption and instability, please replace your changer and cables.'
    elif _throttled == '8000':
        return 'Your Raspberry Pi is overheating, consider getting a fan or heat sinks.'
    else:
        return 'There is a problem with your power supply or system.'


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    client.connect(broker_url, broker_port)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"Temp/config", payload='{"name":"'+ deviceName +'Temperature","state_topic":"system-sensors/sensor/'+ deviceName +'/state","unit_of_measurement":"°C","value_template":"{{ value_json.temperature}}","unique_id":"'+ deviceName.lower() +'_sensor_temperature","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"DiskUse/config", payload='{"name":"'+ deviceName +'DiskUse","state_topic":"system-sensors/sensor/'+ deviceName +'/state","unit_of_measurement":"%","value_template":"{{ value_json.disk_use}}","unique_id":"'+ deviceName.lower() +'_sensor_disk_use","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"MemoryUse/config", payload='{"name":"'+ deviceName +'MemoryUse","state_topic":"system-sensors/sensor/'+ deviceName +'/state","unit_of_measurement":"%","value_template":"{{ value_json.memory_use}}","unique_id":"'+ deviceName.lower() +'_sensor_memory_use","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"CpuUsage/config", payload='{"name":"'+ deviceName +'CpuUsage","state_topic":"system-sensors/sensor/'+ deviceName +'/state","unit_of_measurement":"%","value_template":"{{ value_json.cpu_usage}}","unique_id":"'+ deviceName.lower() +'_sensor_cpu_usage","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"SwapUsage/config", payload='{"name":"'+ deviceName +'SwapUsage","state_topic":"system-sensors/sensor/'+ deviceName +'/state","unit_of_measurement":"%","value_template":"{{ value_json.swap_usage}}","unique_id":"'+ deviceName.lower() +'_sensor_swap_usage","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"PowerStatus/config", payload='{"name":"'+ deviceName +'PowerStatus","state_topic":"system-sensors/sensor/'+ deviceName +'/state","value_template":"{{ value_json.power_status}}","unique_id":"'+ deviceName.lower() +'_sensor_power_status","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    client.publish(topic="homeassistant/sensor/"+ deviceName +"/"+ deviceName +"LastBoot/config", payload='{"device_class":"timestamp","name":"'+ deviceName +'LastBoot","state_topic":"system-sensors/sensor/'+ deviceName +'/state","value_template":"{{ value_json.last_boot}}","unique_id":"'+ deviceName.lower() +'_sensor_last_boot","device":{"identifiers":["'+ deviceName.lower() +'_sensor"],"name":"'+ deviceName +'Sensors","model":"RPI '+ deviceName +'","manufacturer":"RPI"}}', qos=1, retain=True)
    job = Job(interval=timedelta(seconds=WAIT_TIME_SECONDS), execute=updateSensors)
    job.start()
    client.loop_forever()

    while True:
            try:
                time.sleep(1)
            except ProgramKilled:
                print ("Program killed: running cleanup code")
                sys.stdout.flush()
                job.stop()
                break
