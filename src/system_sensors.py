#!/usr/bin/env python3
import argparse
import datetime as dt
import signal
import sys
import socket
import platform
import threading
import time
from datetime import timedelta
from re import findall
from subprocess import check_output
from rpi_bad_power import new_under_voltage
import paho.mqtt.client as mqtt
import psutil
import pytz
import yaml
import csv
from pytz import timezone

try:
    import apt
    apt_disabled = False
except ImportError:
    apt_disabled = True
UTC = pytz.utc
DEFAULT_TIME_ZONE = None

old_net_data = psutil.net_io_counters()
previous_time = time.time()

# Get OS information
OS_DATA = {}
with open("/etc/os-release") as f:
    reader = csv.reader(f, delimiter="=")
    for row in reader:
        if row:
            OS_DATA[row[0]] = row[1]

mqttClient = None
WAIT_TIME_SECONDS = 60
deviceName = None
_underVoltage = None

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


def write_message_to_console(message):
    print(message)
    sys.stdout.flush()


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

def get_last_message():
    return str(as_local(utc_from_timestamp(time.time())).isoformat())


def on_message(client, userdata, message):
    print (f"Message received: {message.payload.decode()}"  )
    if(message.payload.decode() == "online"):
        send_config_message(client)


def updateSensors():
    payload_str = (
        '{'
        + f'"temperature": {get_temp()},'
        + f'"disk_use": {get_disk_usage("/")},'
        + f'"memory_use": {get_memory_usage()},'
        + f'"cpu_usage": {get_cpu_usage()},'
        + f'"swap_usage": {get_swap_usage()},'
        + f'"power_status": "{get_rpi_power_status()}",'
        + f'"last_boot": "{get_last_boot()}",'
        + f'"last_message": "{get_last_message()}",'
        + f'"host_name": "{get_host_name()}",'
        + f'"host_ip": "{get_host_ip()}",'
        + f'"host_os": "{get_host_os()}",'
        + f'"host_arch": "{get_host_arch()}",'
        + f'"load_1m": "{get_load(0)}",'
        + f'"load_5m": "{get_load(1)}",'
        + f'"load_15m": "{get_load(2)}",'
        + f'"net_tx": "{get_net_data()[0]}",'
        + f'"net_rx": "{get_net_data()[1]}"'
    )
    if "check_available_updates" in settings and settings["check_available_updates"] and not apt_disabled:
        payload_str = payload_str + f', "updates": {get_updates()}'
    if "check_wifi_strength" in settings and settings["check_wifi_strength"]:
        payload_str = payload_str + f', "wifi_strength": {get_wifi_strength()}'
    if "check_wifi_ssid" in settings and settings["check_wifi_ssid"]:
        payload_str = payload_str + f', "wifi_ssid": \"{get_wifi_ssid()}\"'
    if "external_drives" in settings:
        for drive in settings["external_drives"]:
            payload_str = (
                payload_str + f', "disk_use_{drive.lower()}": {get_disk_usage(settings["external_drives"][drive])}'
            )
    payload_str = payload_str + "}"
    mqttClient.publish(
        topic=f"system-sensors/sensor/{deviceName}/state",
        payload=payload_str,
        qos=1,
        retain=False,
    )


def get_updates():
    cache = apt.Cache()
    cache.open(None)
    cache.upgrade()
    return str(cache.get_changes().__len__())


# Temperature method depending on system distro
def get_temp():
    temp = "";
    if "rasp" in OS_DATA["ID"]:
        reading = check_output(["vcgencmd", "measure_temp"]).decode("UTF-8")
        temp = str(findall("\d+\.\d+", reading)[0])
    else:
        reading = check_output(["cat", "/sys/class/thermal/thermal_zone0/temp"]).decode("UTF-8")
        temp = str(reading[0] + reading[1] + "." + reading[2])
    return temp

def get_disk_usage(path):
    return str(psutil.disk_usage(path).percent)


def get_memory_usage():
    return str(psutil.virtual_memory().percent)


def get_load(arg):
    return str(psutil.getloadavg()[arg])

def get_net_data():
    global old_net_data
    global previous_time
    current_net_data = psutil.net_io_counters()
    current_time = time.time()
    net_data = (current_net_data[0] - old_net_data[0]) / (current_time - previous_time) * 8 / 1024
    net_data = (net_data, (current_net_data[1] - old_net_data[1]) / (current_time - previous_time) * 8 / 1024)
    previous_time = current_time
    old_net_data = current_net_data
    return ['%.2f' % net_data[0], '%.2f' % net_data[1]]


def get_cpu_usage():
    return str(psutil.cpu_percent(interval=None))


def get_swap_usage():
    return str(psutil.swap_memory().percent)


def get_wifi_strength():  # check_output(["/proc/net/wireless", "grep wlan0"])
    wifi_strength_value = check_output(
                              [
                                  "bash",
                                  "-c",
                                  "cat /proc/net/wireless | grep wlan0: | awk '{print int($4)}'",
                              ]
                          ).decode("utf-8").rstrip()
    if not wifi_strength_value:
        wifi_strength_value = "0"
    return (wifi_strength_value)

def get_wifi_ssid():
    ssid = check_output(
                              [
                                  "bash",
                                  "-c",
                                  "/usr/sbin/iwgetid -r",
                              ]
                          ).decode("utf-8").rstrip()
    if not ssid:
        ssid = "UNKNOWN"
    return (ssid)

def get_rpi_power_status():
    return _underVoltage.get()

def get_host_name():
    return socket.gethostname()

def get_host_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except socket.error:
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            return '127.0.0.1'
    finally:
        sock.close()

def get_host_os():
    try:
        return OS_DATA["PRETTY_NAME"]
    except:
        return "Unknown"

def get_host_arch():
    try:
        return platform.machine()
    except:
        return "Unknown"

def remove_old_topics():
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}Temp/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}DiskUse/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}MemoryUse/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}CpuUsage/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}SwapUsage/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/binary_sensor/{deviceNameDisplay}/{deviceNameDisplay}PowerStatus/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}PowerStatus/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}LastBoot/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}LastMessage/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}WifiStrength/config",
        payload='',
        qos=1,
        retain=False,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}Updates/config",
        payload='',
        qos=1,
        retain=False,
    )

    if "external_drives" in settings:
        for drive in settings["external_drives"]:
            mqttClient.publish(
                topic=f"homeassistant/sensor/{deviceNameDisplay}/{deviceNameDisplay}DiskUse{drive}/config",
                payload='',
                qos=1,
                retain=False,
            )


def check_settings(settings):
    if "mqtt" not in settings:
        write_message_to_console("Mqtt not defined in settings.yaml! Please check the documentation")
        sys.exit()
    if "hostname" not in settings["mqtt"]:
        write_message_to_console("Hostname not defined in settings.yaml! Please check the documentation")
        sys.exit()
    if "timezone" not in settings:
        write_message_to_console("Timezone not defined in settings.yaml! Please check the documentation")
        sys.exit()
    if "deviceName" not in settings:
        write_message_to_console("deviceName not defined in settings.yaml! Please check the documentation")
        sys.exit()
    if "client_id" not in settings:
        write_message_to_console("client_id not defined in settings.yaml! Please check the documentation")
        sys.exit()
    if "power_integer_state" in settings:
        write_message_to_console("power_integer_state is deprecated please remove this option power state is now a binary_sensor!")


def send_config_message(mqttClient):
    write_message_to_console("send config message")
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/temperature/config",
        payload='{"device_class":"temperature",'
                + f"\"name\":\"{deviceNameDisplay} Temperature\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"°C",'
                + '"value_template":"{{value_json.temperature}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_temperature\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:thermometer\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/disk_use/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Disk Use\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"%",'
                + '"value_template":"{{value_json.disk_use}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_disk_use\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:micro-sd\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/memory_use/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Memory Use\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"%",'
                + '"value_template":"{{value_json.memory_use}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_memory_use\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:memory\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/cpu_usage/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Cpu Usage\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"%",'
                + '"value_template":"{{value_json.cpu_usage}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_cpu_usage\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:memory\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/load_1m/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Load 1m\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.load_1m}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_load_1m\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:cpu-64-bit\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/load_5m/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Load 5m\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.load_5m}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_load_5m\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:cpu-64-bit\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/load_15m/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Load 15m\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.load_15m}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_load_15m\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:cpu-64-bit\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/net_tx/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Network Upload\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"Kb/sec",'
                + '"value_template":"{{value_json.net_tx}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_net_tx\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:server-network\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/net_rx/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Network Download\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"Kb/sec",'
                + '"value_template":"{{value_json.net_rx}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_net_rx\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:server-network\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/swap_usage/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Swap Usage\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"unit_of_measurement":"%",'
                + '"value_template":"{{value_json.swap_usage}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_swap_usage\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:harddisk\"}}",
        qos=1,
        retain=True,
    )

    mqttClient.publish(
        topic=f"homeassistant/binary_sensor/{deviceName}/power_status/config",
        payload='{"device_class":"problem",'
                + f"\"name\":\"{deviceNameDisplay} Under Voltage\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.power_status}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_power_status\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}}"
                + f"}}",
        qos=1,
        retain=True,
    )


    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/last_boot/config",
        payload='{"device_class":"timestamp",'
                + f"\"name\":\"{deviceNameDisplay} Last Boot\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.last_boot}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_last_boot\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:clock\"}}",
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/hostname/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Hostname\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.host_name}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_host_name\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:card-account-details\"}}",
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/host_ip/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Host Ip\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.host_ip}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_host_ip\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:lan\"}}",
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/host_os/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Host OS\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.host_os}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_host_os\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:linux\"}}",
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/host_arch/config",
        payload=f"{{\"name\":\"{deviceNameDisplay} Host Architecture\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.host_arch}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_host_arch\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:chip\"}}",
        qos=1,
        retain=True,
    )
    mqttClient.publish(
        topic=f"homeassistant/sensor/{deviceName}/last_message/config",
        payload='{"device_class":"timestamp",'
                + f"\"name\":\"{deviceNameDisplay} Last Message\","
                + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                + '"value_template":"{{value_json.last_message}}",'
                + f"\"unique_id\":\"{deviceName}_sensor_last_message\","
                + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                + f"\"icon\":\"mdi:clock-check\"}}",
        qos=1,
        retain=True,
    )


    if "check_available_updates" in settings and settings["check_available_updates"]:
        # import apt
        if(apt_disabled):
            write_message_to_console("import of apt failed!")
        else:
            mqttClient.publish(
                topic=f"homeassistant/sensor/{deviceName}/updates/config",
                payload=f"{{\"name\":\"{deviceNameDisplay} Updates\","
                        + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                        + '"value_template":"{{value_json.updates}}",'
                        + f"\"unique_id\":\"{deviceName}_sensor_updates\","
                        + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                        + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                        + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                        + f"\"icon\":\"mdi:cellphone-arrow-down\"}}",
                qos=1,
                retain=True,
            )


    if "check_wifi_strength" in settings and settings["check_wifi_strength"]:
        mqttClient.publish(
            topic=f"homeassistant/sensor/{deviceName}/wifi_strength/config",
            payload='{"device_class":"signal_strength",'
                    + f"\"name\":\"{deviceNameDisplay} Wifi Strength\","
                    + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                    + '"unit_of_measurement":"dBm",'
                    + '"value_template":"{{value_json.wifi_strength}}",'
                    + f"\"unique_id\":\"{deviceName}_sensor_wifi_strength\","
                    + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                    + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                    + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                    + f"\"icon\":\"mdi:wifi\"}}",
            qos=1,
            retain=True,
        )


    if "check_wifi_ssid" in settings and settings["check_wifi_ssid"]:
        mqttClient.publish(
            topic=f"homeassistant/sensor/{deviceName}/wifi_ssid/config",
            payload='{"device_class":"signal_strength",'
                    + f"\"name\":\"{deviceNameDisplay} Wifi SSID\","
                    + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                    + '"value_template":"{{value_json.wifi_ssid}}",'
                    + f"\"unique_id\":\"{deviceName}_sensor_wifi_ssid\","
                    + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                    + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                    + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                    + f"\"icon\":\"mdi:wifi\"}}",
            qos=1,
            retain=True,
        )

    if "external_drives" in settings:
        for drive in settings["external_drives"]:
            mqttClient.publish(
                topic=f"homeassistant/sensor/{deviceName}/disk_use_{drive.lower()}/config",
                payload=f"{{\"name\":\"{deviceNameDisplay} Disk Use {drive}\","
                        + f"\"state_topic\":\"system-sensors/sensor/{deviceName}/state\","
                        + '"unit_of_measurement":"%",'
                        + f"\"value_template\":\"{{{{value_json.disk_use_{drive.lower()}}}}}\","
                        + f"\"unique_id\":\"{deviceName}_sensor_disk_use_{drive.lower()}\","
                        + f"\"availability_topic\":\"system-sensors/sensor/{deviceName}/availability\","
                        + f"\"device\":{{\"identifiers\":[\"{deviceName}_sensor\"],"
                        + f"\"name\":\"{deviceNameDisplay} Sensors\",\"model\":\"RPI {deviceNameDisplay}\", \"manufacturer\":\"RPI\"}},"
                        + f"\"icon\":\"mdi:harddisk\"}}",
                qos=1,
                retain=True,
            )


    mqttClient.publish(f"system-sensors/sensor/{deviceName}/availability", "online", retain=True)


def _parser():
    """Generate argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument("settings", help="path to the settings file")
    return parser


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        write_message_to_console("Connected to broker")
        client.subscribe("hass/status")
        mqttClient.publish(f"system-sensors/sensor/{deviceName}/availability", "online", retain=True)
    else:
        write_message_to_console("Connection failed")


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
    mqttClient.on_connect = on_connect                      #attach function to callback
    mqttClient.on_message = on_message
    deviceName = settings["deviceName"].replace(" ", "").lower()
    deviceNameDisplay = settings["deviceName"]
    mqttClient.will_set(f"system-sensors/sensor/{deviceName}/availability", "offline", retain=True)
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
    try:
        remove_old_topics()
        send_config_message(mqttClient)
    except:
        write_message_to_console("something whent wrong")
    _underVoltage = new_under_voltage()
    job = Job(interval=timedelta(seconds=WAIT_TIME_SECONDS), execute=updateSensors)
    job.start()

    mqttClient.loop_start()

    while True:
        try:
            sys.stdout.flush()
            time.sleep(1)
        except ProgramKilled:
            write_message_to_console("Program killed: running cleanup code")
            mqttClient.publish(f"system-sensors/sensor/{deviceName}/availability", "offline", retain=True)
            mqttClient.disconnect()
            mqttClient.loop_stop()
            sys.stdout.flush()
            job.stop()
            break