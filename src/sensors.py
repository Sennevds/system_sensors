#!/usr/bin/env python3

import time, pytz, psutil, socket, platform, subprocess
from datetime import datetime as dt, timedelta as td
from console_colours import *

rpi_power_disabled = True
under_voltage = None
apt_disabled = True

_os_data = {}
_previous_net_data = psutil.net_io_counters()
_previous_time = time.time() - 10
_default_timezone = None
_utc = pytz.utc

# Test for Raspberry PI power module
try:
    from rpi_bad_power import new_under_voltage
    if new_under_voltage() is not None:
        # Only enable if import works and function returns a value
        rpi_power_disabled = False
        under_voltage = new_under_voltage()
except ImportError:
    pass

# Test for APT module
try:
    import apt
    apt_disabled = False
except ImportError:
    pass

# Get OS information
with open('/etc/os-release') as f:
    for line in f.readlines():
        row = line.strip().split("=")
        _os_data[row[0]] = row[1].strip('"')

def set_default_timezone(timezone) -> None:
    global _default_timezone
    _default_timezone = timezone

def as_local(dattim: dt) -> dt:
    global _default_timezone
    """Convert a UTC datetime object to local time zone."""
    if dattim.tzinfo == _default_timezone:
        return dattim
    if dattim.tzinfo is None:
        dattim = _utc.localize(dattim)

    return dattim.astimezone(_default_timezone)

def utc_from_timestamp(timestamp: float) -> dt:
    """Return a UTC time from a timestamp."""
    return _utc.localize(dt.utcfromtimestamp(timestamp))

def get_last_boot() -> str:
    return str(as_local(utc_from_timestamp(psutil.boot_time())).isoformat())

def get_last_message() -> str:
    return str(as_local(utc_from_timestamp(time.time())).isoformat())

def get_updates() -> int:
    cache = apt.Cache()
    cache.open(None)
    cache.upgrade()
    return cache.get_changes().__len__()

# Temperature method depending on system distro
def get_temp() -> float:
    temp = 'Unknown'
    # Utilising psutil for temp reading on ARM arch
    try:
        temp = psutil.sensors_temperatures()['cpu_thermal'][0].current
    except:
        try:
            # Assumes that first entry is the CPU package, have not tested this on other systems except my NUC x86
            temp = psutil.sensors_temperatures()['coretemp'][0].current
        except Exception as e:
            write_message_to_console(f'Could not establish CPU temperature reading: {text_color.B_FAIL}{e}', tab=1, status='warning')
            raise
    return round(temp, 1)

def get_clock_speed() -> int:
    clock_speed = int(psutil.cpu_freq().current)
    return clock_speed

def get_disk_usage(path) -> float:
    try:
        disk_percentage = psutil.disk_usage(path).percent
        return disk_percentage
    except Exception as e:
        write_message_to_console(f'Could not get disk usage from {text_color.B_WHITE}{path}{text_color.RESET}: {text_color.B_FAIL}{e}', tab=1, status='warning')
        raise

def get_memory_usage() -> float:
    return str(psutil.virtual_memory().percent)

def get_load(arg) -> float:
    return str(psutil.getloadavg()[arg])

def get_net_data(arg) -> float:
    global _previous_net_data
    global _previous_time
    current_net_data = psutil.net_io_counters()
    current_time = time.time()
    if current_time == _previous_time:
        current_time += 1
    net_data = (current_net_data[0] - _previous_net_data[0]) / (current_time - _previous_time) * 8 / 1024
    net_data = (net_data, (current_net_data[1] - _previous_net_data[1]) / (current_time - _previous_time) * 8 / 1024)
    _previous_time = current_time
    _previous_net_data = current_net_data
    net_data = ['%.2f' % net_data[0], '%.2f' % net_data[1]]
    return net_data[arg]

def get_cpu_usage() -> float:
    return str(psutil.cpu_percent(interval=None))

def get_swap_usage() -> float:
    return str(psutil.swap_memory().percent)

def get_wifi_strength() -> int:
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

def get_wifi_ssid() -> str:
    ssid = 'UNKNOWN'
    try:
        ssid = subprocess.check_output(
                                  [
                                      'bash',
                                      '-c',
                                      '/usr/sbin/iwgetid -r',
                                  ]
                              ).decode('utf-8').rstrip()
        print(ssid)
    except Exception as e:
        write_message_to_console(f'Could not deterine WiFi SSID: {text_color.B_FAIL}{e}', tab=1, status='warning')
    
    print(ssid)
    return ssid

def get_rpi_power_status() -> str:
    return under_voltage.get()

def get_hostname() -> str:
    return socket.gethostname()

def get_host_ip() -> str:
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

def get_host_os() -> str:
    try:
        return _os_data['PRETTY_NAME']
    except:
        return 'Unknown'

def get_host_arch() -> str:
    try:
        return platform.machine()
    except:
        return 'Unknown'

def external_drive_base(drive, drive_path) -> dict:
    return {
        'name': f'Disk Use {drive}',
        'unit': '%',
        'icon': 'harddisk',
        'sensor_type': 'sensor',
        'function': lambda: get_disk_usage(f'{drive_path}')
        }

sensor_objects = {
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