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


# Get OS information
OS_DATA = {}
with open('/etc/os-release') as f:
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
    temp = 'Unknown'
    # Utilising psutil for temp reading on ARM arch
    try:
        t = psutil.sensors_temperatures()
        for x in ['cpu-thermal', 'cpu_thermal']:
            if x in t:
                temp = t[x][0].current
                break
    except:
        try:
            # Assumes that first entry is the CPU package, have not tested this on other systems except my NUC x86
            temp = psutil.sensors_temperatures()['coretemp'][0].current
        except Exception as e:
            print('Could not establish CPU temperature reading: ' + str(e))
            raise
    return round(temp, 1)

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
    return 'ON' if _underVoltage.get() else 'OFF'

def get_hostname():
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

sensors = {
          'temperature': 
                {'name':'Temperature',
                 'class': 'temperature',
                 'unit': '°C',
                 'icon': 'thermometer',
                 'sensor_type': 'sensor',
                 'function': get_temp},
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