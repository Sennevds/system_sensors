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
import shutil
import json
# import os.path

class PropertyBag(dict):
    def to_string(self, device_name:str):
        for key in self.keys():
            self[key] = str.replace(self[key], "{device_name}", device_name)
        return str.replace(str.replace(json.dumps(self), "{", ''), "}", '')

# Only needed if using alternate method of obtaining CPU temperature (see commented out code for approach)
#from os import walk


rpi_power_disabled = True
try:
    from rpi_bad_power import new_under_voltage
    if new_under_voltage() is not None:
        # Only enable if import works and function returns a value
        rpi_power_disabled = False
except ImportError:
    pass

try:
    import apt
    apt_disabled = False
except ImportError:
    apt_disabled = True

isDockerized = bool(os.getenv('YES_YOU_ARE_IN_A_CONTAINER', False))
isOsRelease = os.path.isfile('/app/host/os-release')
isHostname = os.path.isfile('/app/host/hostname')
isDeviceTreeModel = os.path.isfile('/app/host/proc/device-tree/model')
isSystemSensorPipe = os.path.isfile('/app/host/system_sensor_pipe')

vcgencmd   = "vcgencmd"
os_release = "/etc/os-release"
if isDockerized:
    os_release = "/app/host/os-release" if isOsRelease else '/etc/os-release'
    vcgencmd   = "/opt/vc/bin/vcgencmd"

# Get OS information
OS_DATA = {}
with open(os_release) as f:
    for line in f.readlines():
        if not line in ['\n', '\r\n']:
            row = line.strip().split("=")
            OS_DATA[row[0]] = row[1].strip('"')

old_net_data_tx = psutil.net_io_counters()[0]
previous_time_tx = time.time() - 10
old_net_data_rx = psutil.net_io_counters()[1]
previous_time_rx = time.time() - 10
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
    # Note that 'Unknown' can be problematic if no temp sensor is found, see get_fan_speed for the reason.
    # Alternatively, the default can be changed to -273 which is unlikely to happen...
    temp = 'Unknown'
    # Utilising psutil for temp reading on ARM arch
    try:
        t = psutil.sensors_temperatures()
        for x in ['cpu-thermal', 'cpu_thermal', 'coretemp', 'soc_thermal', 'k10temp']:
            if x in t:
                temp = t[x][0].current
                break
    except Exception as e:
            print('Could not establish CPU temperature reading: ' + str(e))
            raise
    return round(temp, 1) if temp != 'Unknown' else temp

            # Option to use thermal_zone readings instead of psutil

            # base_dir = '/sys/class/thermal/'
            # zone_dir = ''
            # print('Could not cpu_thermal property. Checking thermal zone for x86 architecture')
            # for root, dir, files in walk(base_dir):
            #     for d in dir:
            #         if 'thermal_zone' in d:
            #             temp_type = str(subprocess.check_output(['cat', base_dir + d + '/type']).decode('UTF-8'))
            #             if 'x86' in temp_type:
            #                 zone_dir = d
            #                 break
            # temp = str(int(subprocess.check_output(['cat', base_dir + zone_dir + '/temp']).decode('UTF-8')) / 1000)


def get_fan_speed():
    # Formerly the default was 'Unknown' which generates in HA a string/number mismatch error if no fan is found
    speed = -1
    # Utilising psutil for fan speed reading on ARM arch
    try:
        if not hasattr(psutil, "sensors_fans"):
            raise NotImplementedError("Platform does not support sensors_fans")

        t = psutil.sensors_fans()
        # if additional fan names returned by psutil are needed, add them here (see get_temp as example)
        for x in ['pwmfan', ]:
            if x in t:
                speed = t[x][0].current
                break
    except (Exception, NotImplementedError) as e:
        print('Could not establish fan speed reading: ' + str(e))
        raise
    return round(speed, 0)


# display power method depending on system distro
def get_display_status():
    if "rasp" in OS_DATA["ID"]:
        reading = subprocess.check_output([vcgencmd, "display_power"]).decode("UTF-8")
        display_state = str(re.findall("^display_power=(?P<display_state>[01]{1})$", reading)[0])
    else:
        display_state = "Unknown"
    return display_state

# Replaced with psutil method - does this not work fine?
def get_clock_speed():
    clock_speed = int(psutil.cpu_freq().current)
    return clock_speed

def get_disk_usage(path):
    try:
        disk_percentage = str(psutil.disk_usage(path).percent)
        return disk_percentage
    except Exception as e:
        print('Error while trying to obtain disk usage from ' + str(path) + ' with exception: ' + str(e))
        return None # Changed to return None for handling exception at function call location

def get_zpool_use(pool):
    zpool_locations = ['/usr/sbin/zpool', '/sbin/zpool']
    zpool_binary = shutil.which("zpool") or next(filter(lambda l: os.path.isfile(l), zpool_locations), None)
    try:
        zpool_percentage = str(subprocess.check_output(
            [
                zpool_binary,
                'list',
                '-H',
                '-o',
                'capacity',
                '-p',
                pool
            ], timeout=2
        ).decode('utf-8')).strip('\n')
        return zpool_percentage
    except Exception as e:
        print('Error while trying to obtain zpool usage from ' +
              str(pool) + ' with exception: ' + str(e))
        return None  # Changed to return None for handling exception at function call location

def get_memory_usage():
    return str(psutil.virtual_memory().percent)

def get_load(arg):
    return round(psutil.getloadavg()[arg] / psutil.cpu_count() * 100, 1)

def get_net_data_tx(interface = True):
    global old_net_data_tx
    global previous_time_tx
    current_net_data = []
    if type(interface) == str:
        current_net_data = psutil.net_io_counters(pernic=True)[interface][0]
    else:
        current_net_data = psutil.net_io_counters()[0]
    current_time = time.time()
    if current_time == previous_time_tx:
        current_time += 1
    net_data = (current_net_data - old_net_data_tx) * 8 / (current_time - previous_time_tx) / 1024
    previous_time_tx = current_time
    old_net_data_tx = current_net_data
    return f"{net_data:.2f}"

def get_net_data_rx(interface = True):
    global old_net_data_rx
    global previous_time_rx
    current_net_data = []
    if type(interface) == str:
        current_net_data = psutil.net_io_counters(pernic=True)[interface][1]
    else:
        current_net_data = psutil.net_io_counters()[1]
    current_time = time.time()
    if current_time == previous_time_rx:
        current_time += 1
    net_data = (current_net_data - old_net_data_rx) * 8 / (current_time - previous_time_rx) / 1024
    previous_time_rx = current_time
    old_net_data_rx = current_net_data
    return f"{net_data:.2f}"

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
    return 'ON' if _underVoltage.get() else 'OFF'

def get_hostname():
    if isDockerized and isHostname:
        host = subprocess.check_output(["cat", "/app/host/hostname"]).decode("UTF-8").strip()
    else:
        host = socket.gethostname()
    return host

def get_host_ip():
    if isDockerized and isSystemSensorPipe:
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

# Builds an external drive entry to fix incorrect usage reporting
def external_drive_base(drive, drive_path) -> dict:
    return {
        'name': f'Disk Use {drive}',
        'unit': '%',
        'icon': 'harddisk',
        'sensor_type': 'sensor',
        'function': lambda: get_disk_usage(f'{drive_path}')
        }

# Builds a zpool entry to fix incorrect usage reporting
def zpool_base(pool) -> dict:
    return {
        'name': f'Zpool Use {pool}',
        'unit': '%',
        'icon': 'harddisk',
        'sensor_type': 'sensor',
        'function': lambda: get_zpool_use(f'{pool}')
        }

sensors = {
          'temperature':
                {'name':'Temperature',
                 'class': 'temperature',
                 'state_class':'measurement',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'sensor_type': 'sensor',
                 'function': get_temp},
            'fan_speed':
                {'name': 'Fan Speed',
                 'state_class': 'measurement',
                 'unit': 'rpm',
                 'icon': 'fan',
                 'sensor_type': 'sensor',
                 'function': get_fan_speed},
          'display':
                {'name':'Display Switch',
                 'icon': 'monitor',
                 'sensor_type': 'switch',
                 'function': get_display_status,
                 'prop': PropertyBag({
                     'command_topic'      : 'system-sensors/sensor/{device_name}/command',
                     'state_off'          : '0',
                     'state_on'           : '1',
                     'payload_off'        : 'display_off',
                     'payload_on'         : 'display_on',
                 })},
          'clock_speed':
                {'name':'Clock Speed',
                 'state_class':'measurement',
                 'unit': 'MHz',
                 'sensor_type': 'sensor',
                 'function': get_clock_speed},
          'disk_use':
                {'name':'Disk Use',
                 'state_class':'measurement',
                 'unit': '%',
                 'icon': 'micro-sd',
                 'sensor_type': 'sensor',
                 'function': lambda: get_disk_usage('/')},
          'memory_use':
                {'name':'Memory Use',
                 'state_class':'measurement',
                 'unit': '%',
                 'icon': 'memory',
                 'sensor_type': 'sensor',
                 'function': get_memory_usage},
          'cpu_usage':
                {'name':'CPU Usage',
                 'state_class':'measurement',
                 'unit': '%',
                 'icon': 'chip',
                 'sensor_type': 'sensor',
                 'function': get_cpu_usage},
          'load_1m':
                {'name': 'Load 1m',
                 'unit': '%',
                 'state_class':'measurement',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(0)},
          'load_5m':
                {'name': 'Load 5m',
                 'unit': '%',
                 'state_class':'measurement',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(1)},
          'load_15m':
                {'name': 'Load 15m',
                 'unit': '%',
                 'state_class':'measurement',
                 'icon': 'cpu-64-bit',
                 'sensor_type': 'sensor',
                 'function': lambda: get_load(2)},
          'net_tx':
                {'name': 'Network Upload',
                 'state_class':'measurement',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': get_net_data_tx},
          'net_rx':
                {'name': 'Network Download',
                 'state_class':'measurement',
                 'unit': 'Kbps',
                 'icon': 'server-network',
                 'sensor_type': 'sensor',
                 'function': get_net_data_rx},
          'swap_usage':
                {'name':'Swap Usage',
                 'state_class':'measurement',
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
                 'state_class':'measurement',
                 'name':'Wifi Strength',
                 'unit': 'dBm',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_strength},
          'wifi_ssid':
                {'name':'Wifi SSID',
                 'icon': 'wifi',
                 'sensor_type': 'sensor',
                 'function': get_wifi_ssid},
          }

