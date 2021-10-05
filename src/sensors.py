#!/usr/bin/env python3

import re
import time
import pytz
import psutil
import socket
import platform
import subprocess
import datetime as dt
import sys
import os

class ProperyBag(dict):
    def to_string(self, device_name:str):
        return str.replace(str.replace(str.replace(self.__str__(), "{device_name}", device_name), "{", ''), "}", '')

try:
    from rpi_bad_power import new_under_voltage
    rpi_power_disabled = False
except ImportError:
    rpi_power_disabled = True

try:
    import apt
    apt_disabled = False
except ImportError:
    apt_disabled = True

isDockerized = bool(os.getenv('YES_YOU_ARE_IN_A_CONTAINER', False))

vcgencmd   = "vcgencmd"
os_release = "/etc/os-release"
if isDockerized:
    os_release = "/app/host/os-release"
    vcgencmd   = "/opt/vc/bin/vcgencmd"

# Get OS information
OS_DATA = {}
with open(os_release) as f:
    for line in f.readlines():
        row = line.strip().split("=")
        OS_DATA[row[0]] = row[1].strip('"')

old_net_data = psutil.net_io_counters()
previous_time = time.time() - 10
UTC = pytz.utc
DEFAULT_TIME_ZONE = None

if not rpi_power_disabled:
    _underVoltage = new_under_voltage()

def set_default_timezone(timezone):
    global DEFAULT_TIME_ZONE
    DEFAULT_TIME_ZONE = timezone


def write_message_to_console(message):
    print(message)
    sys.stdout.flush()

def as_local(dattim: dt.datetime) -> dt.datetime:
    global DEFAULT_TIME_ZONE
    """Convert a UTC datetime object to local time zone."""
    if dattim.tzinfo == DEFAULT_TIME_ZONE:
        return dattim
    if dattim.tzinfo is None:
        dattim = UTC.localize(dattim)

    return dattim.astimezone(DEFAULT_TIME_ZONE)

def utc_from_timestamp(timestamp: float) -> dt.datetime:
    """Return a UTC time from a timestamp."""
    return UTC.localize(dt.datetime.utcfromtimestamp(timestamp))

def get_last_boot():
    return str(as_local(utc_from_timestamp(psutil.boot_time())).isoformat())

def get_last_message():
    return str(as_local(utc_from_timestamp(time.time())).isoformat())

def get_updates():
    cache = apt.Cache()
    cache.open(None)
    cache.upgrade()
    return str(cache.get_changes().__len__())

# Temperature method depending on system distro
def get_temp():
    temp = ''
    if 'rasp' in OS_DATA['ID']:
        reading = subprocess.check_output([vcgencmd, 'measure_temp']).decode('UTF-8')
        temp = str(re.findall('\d+.\d+', reading)[0])
    else:
        reading = subprocess.check_output(['cat', '/sys/class/thermal/thermal_zone0/temp']).decode('UTF-8')
        temp = str(reading[0] + reading[1] + '.' + reading[2]) # why?? need linux system to test
    return temp

# display power method depending on system distro
def get_display_status():
    if "rasp" in OS_DATA["ID"]:
        reading = subprocess.check_output([vcgencmd, "display_power"]).decode("UTF-8")
        display_state = str(re.findall("^display_power=(?P<display_state>[01]{1})$", reading)[0])
    else:
        display_state = "Unknown"
    return display_state

# Clock speed method depending on system distro
def get_clock_speed():
    clock_speed = ''
    if 'rasp' in OS_DATA['ID']:
        reading = subprocess.check_output([vcgencmd, 'measure_clock','arm']).decode('UTF-8')
        clock_speed = str(int(re.findall('\d+', reading)[1]) / 1000000)
    else: # need linux system to test
        reading = subprocess.check_output(['cat', '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq']).decode('UTF-8')
        clock_speed = str(int(re.findall('\d+', reading)[0]) / 1000)
    return clock_speed

def get_disk_usage(path):
    return str(psutil.disk_usage(path).percent)


def get_memory_usage():
    return str(psutil.virtual_memory().percent)


def get_load(arg):
    return str(psutil.getloadavg()[arg])

def get_net_data(arg):
    global old_net_data
    global previous_time
    current_net_data = psutil.net_io_counters()
    current_time = time.time()
    if current_time == previous_time:
        current_time += 1
    net_data = (current_net_data[0] - old_net_data[0]) / (current_time - previous_time) * 8 / 1024
    net_data = (net_data, (current_net_data[1] - old_net_data[1]) / (current_time - previous_time) * 8 / 1024)
    previous_time = current_time
    old_net_data = current_net_data
    net_data = ['%.2f' % net_data[0], '%.2f' % net_data[1]]
    return net_data[arg]

def get_cpu_usage():
    return str(psutil.cpu_percent(interval=None))

def get_swap_usage():
    return str(psutil.swap_memory().percent)

def get_wifi_strength():  # subprocess.check_output(['/proc/net/wireless', 'grep wlan0'])
    wifi_strength_value = subprocess.check_output(
                              [
                                  'bash',
                                  '-c',
                                  'cat /proc/net/wireless | grep wlan0: | awk \'{print int($4)}\'',
                              ]
                          ).decode('utf-8').rstrip()
    if not wifi_strength_value:
        wifi_strength_value = '0'
    return (wifi_strength_value)

def get_wifi_ssid():
    try:
        ssid = subprocess.check_output(
                                  [
                                      'bash',
                                      '-c',
                                      '/usr/sbin/iwgetid -r',
                                  ]
                              ).decode('utf-8').rstrip()
    except subprocess.CalledProcessError:
        ssid = 'UNKNOWN'
    if not ssid:
        ssid = 'UNKNOWN'
    return (ssid)

def get_rpi_power_status():
    return _underVoltage.get()

def get_hostname():
    if isDockerized:
        # todo add a check to validate the file actually exists, in case someone forgot to map it
        host = subprocess.check_output(["cat", "/app/host/hostname"]).decode("UTF-8").strip()
    else:
        host = socket.gethostname()
    return host

def get_host_ip():
    if isDockerized:
        return get_container_host_ip()
    else:
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

def get_container_host_ip():
    # todo add a check to validate the file actually exists, in case someone forgot to map it
     data = subprocess.check_output(["cat", "/app/host/system_sensor_pipe"]).decode("UTF-8")
     ip = ""
     for line in data.split('\n'):
         mo = re.match ("^.{2}(?P<id>.{2}).{2}(?P<addr>.{8})..{4} .{8}..{4} (?P<status>.{2}).*|", line)
         if mo and mo.group("id") != "sl":
             status = int(mo.group("status"), 16)
             if status == 1: # connection established
                 ip = hex2addr(mo.group("addr"))
                 break
     return ip

def hex2addr(hex_addr):
    l = len(hex_addr)
    first = True
    ip = ""
    for i in range(l // 2):
        if (first != True):
            ip = "%s." % ip
        else:
            first = False
        ip = ip + ("%d" % int(hex_addr[-2:], 16))
        hex_addr = hex_addr[:-2]
    return ip

def get_host_os():
    try:
        return OS_DATA['PRETTY_NAME']
    except:
        return 'Unknown'

def get_host_arch():
    try:
        return platform.machine()
    except:
        return 'Unknown'

sensors = {
          'temperature':
                {'name':'Temperature',
                 'class': 'temperature',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'sensor_type': 'sensor',
                 'function': get_temp},
          'display':
                {'name':'Display Switch',
                 'icon': 'monitor',
                 'sensor_type': 'switch',
                 'function': get_display_status,
                 'prop': ProperyBag({
                     'availability_topic' : "system-sensors/sensor/{device_name}/availability",
                     'command_topic'      : 'system-sensors/sensor/{device_name}/command',
                     'state_topic'        : 'system-sensors/sensor/{device_name}/state',
                     'value_template'     : '{{value_json.display}}',
                     'state_off'          : '0',
                     'state_on'           : '1',
                     'payload_off'        : 'display_off',
                     'payload_on'         : 'display_on',
                 })},
          'clock_speed':
                {'name':'Clock Speed',
                 'unit': 'MHz',
                 'sensor_type': 'sensor',
                 'function': get_clock_speed},
          'disk_use':
                {'name':'Disk Use',
                 'unit': '%',
                 'icon': 'micro-sd',
                 'sensor_type': 'sensor',
                 'function': lambda: get_disk_usage('/')},
          'memory_use':
                {'name':'Memory Use',
                 'unit': '%',
                 'icon': 'memory',
                 'sensor_type': 'sensor',
                 'function': get_memory_usage},
          'cpu_usage':
                {'name':'CPU Usage',
                 'unit': '%',
                 'icon': 'memory',
                 'sensor_type': 'sensor',
                 'function': get_cpu_usage},
          'load_1m':
                {'name': 'Load 1m',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(0)},
          'load_5m':
                {'name': 'Load 5m',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(1)},
          'load_15m':
                {'name': 'Load 15m',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(2)},
          'net_tx':
                {'name': 'Network Upload',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': lambda: get_net_data(0)},
          'net_rx':
                {'name': 'Network Download',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': lambda: get_net_data(1)},
          'swap_usage':
                {'name':'Swap Usage',
                 'unit': '%',
                 'icon': 'harddisk',
                 'sensor_type': 'sensor',
                 'function': get_swap_usage},
          'power_status':
                {'name': 'Under Voltage',
                 'class': 'problem',
                 'sensor_type': 'binary_sensor',
                 'function': get_rpi_power_status},
          'last_boot':
                {'name': 'Last Boot',
                 'class': 'timestamp',
                 'icon': 'clock',
                 'sensor_type': 'sensor',
                 'function': get_last_boot},
          'hostname':
                {'name': 'Hostname',
                 'icon': 'card-account-details',
                 'sensor_type': 'sensor',
                 'function': get_hostname},
          'host_ip':
                {'name': 'Host IP',
                 'icon': 'lan',
                 'sensor_type': 'sensor',
                 'function': get_host_ip},
          'host_os':
                {'name': 'Host OS',
                 'icon': 'linux',
                 'sensor_type': 'sensor',
                 'function': get_host_os},
          'host_arch':
                {'name': 'Host Architecture',
                 'icon': 'chip',
                 'sensor_type': 'sensor',
                 'function': get_host_arch},
          'last_message':
                {'name': 'Last Message',
                 'class': 'timestamp',
                 'icon': 'clock-check',
                 'sensor_type': 'sensor',
                 'function': get_last_message},
          'updates':
                {'name':'Updates',
                 'icon': 'cellphone-arrow-down',
                 'sensor_type': 'sensor',
                 'function': get_updates},
          'wifi_strength':
                {'class': 'signal_strength',
                 'name':'Wifi Strength',
                 'unit': 'dBm',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_strength},
          'wifi_ssid':
                {'class': 'signal_strength',
                 'name':'Wifi SSID',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_ssid},
          }

