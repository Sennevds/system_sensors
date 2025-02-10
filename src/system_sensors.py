#!/usr/bin/env python3

from os import error, path
import sys
import time
import yaml
import signal
import pathlib
import argparse
import threading
import paho.mqtt.client as mqtt
import importlib.metadata

from sensors import *


mqttClient = None
global poll_interval
devicename = None
settings = {}
external_drives = []

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



def update_sensors():
    payload_str = f'{{'
    for sensor, attr in sensors.items():
        # Skip sensors that have been disabled or are missing
        if sensor in external_drives:
            payload_str += f'"{sensor}": "{attr["function"]()}",'
        elif settings['sensors'][sensor] is not None:
            if settings['sensors'][sensor] == True:
                payload_str += f'"{sensor}": "{attr["function"]()}",'
            elif settings['sensors'][sensor] is not False:
                payload_str += f'"{sensor}": "{attr["function"](settings["sensors"][sensor])}",'

    payload_str = payload_str[:-1]
    payload_str += f'}}'
    mqttClient.publish(
        topic=f'system-sensors/{attr["sensor_type"]}/{devicename}/state',
        payload=payload_str,
        qos=1,
        retain=False,
    )


def send_config_message(mqttClient):

    write_message_to_console('Sending config message to host...')

    for sensor, attr in sensors.items():
        try:
            # Added check in case sensor is an external drive, which is nested in the config
            if sensor in external_drives or settings['sensors'][sensor]:
                mqttClient.publish(
                    topic=f'homeassistant/{attr["sensor_type"]}/{devicename}/{sensor}/config',
                    payload = (f'{{'
                                + (f'"device_class":"{attr["class"]}",' if 'class' in attr else '')
                                + (f'"state_class":"{attr["state_class"]}",' if 'state_class' in attr else '')
                                + f'"name":"{attr["name"]}",'
                                + f'"state_topic":"system-sensors/sensor/{devicename}/state",'
                                + (f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else '')
                                + f'"value_template":"{{{{value_json.{sensor}}}}}",'
                                + f'"object_id":"{devicename}_{attr["sensor_type"]}_{sensor}",'
                                + f'"unique_id":"{devicename}_{attr["sensor_type"]}_{sensor}",'
                                + f'"availability_topic":"system-sensors/sensor/{devicename}/availability",'
                                + f'"device":{{"identifiers":["{devicename}_sensor"],'
                                + f'"name":"{deviceNameDisplay} Sensors","model":"{deviceModel}", "manufacturer":"{deviceManufacturer}"}}'
                                + (f',"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else '')
                                + (f',{attr["prop"].to_string(devicename)}' if 'prop' in attr else '')
                                + f'}}'
                    ),
                    qos=1,
                    retain=True,
                )
        except Exception as e:
            write_message_to_console('An error was produced while processing ' + str(sensor) + ' with exception: ' + str(e))
            print(str(settings))
            raise

    mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'online', retain=True)

def _parser():
    """Generate argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument('settings', help='path to the settings file')
    return parser

def set_defaults(settings):
    global poll_interval
    set_default_timezone(pytz.timezone(settings['timezone']))
    poll_interval = settings['update_interval'] if 'update_interval' in settings else 60
    if 'port' not in settings['mqtt']:
        settings['mqtt']['port'] = 1883
    if 'sensors' not in settings:
        settings['sensors'] = {}
    for sensor in sensors:
        if sensor not in settings['sensors']:
            settings['sensors'][sensor] = True
    if 'external_drives' not in settings['sensors'] or settings['sensors']['external_drives'] is None:
        settings['sensors']['external_drives'] = {}
    if "rasp" not in OS_DATA["ID"]:
        settings['sensors']['display'] = False

    # 'settings' argument is local, so needs to be returned to overwrite the one in the main function
    return settings

def check_settings(settings):
    values_to_check = ['mqtt', 'timezone', 'devicename', 'client_id']
    for value in values_to_check:
        if value not in settings:
            write_message_to_console(value + ' not defined in settings.yaml! Please check the documentation')
            sys.exit()
    if 'hostname' not in settings['mqtt']:
        write_message_to_console('hostname not defined in settings.yaml! Please check the documentation')
        sys.exit()
    if 'user' in settings['mqtt'] and 'password' not in settings['mqtt']:
        write_message_to_console('password not defined in settings.yaml! Please check the documentation')
        sys.exit()
    if 'power_status' in settings['sensors'] and rpi_power_disabled:
        write_message_to_console('Unable to import rpi_bad_power library, or is incompatible on host architecture. Power supply info will not be shown.')
        settings['sensors']['power_status'] = False
    if 'updates' in settings['sensors'] and apt_disabled:
        write_message_to_console('Unable to import apt package. Available updates will not be shown.')
        settings['sensors']['updates'] = False
    if 'power_integer_state' in settings:
        write_message_to_console('power_integer_state is deprecated please remove this option power state is now a binary_sensor!')
    # these two may be present or not, but in case they are not, create a default
    if 'ha_status' not in settings or settings['ha_status'] == '':
        settings['ha_status'] = 'hass'
    if 'tls' not in settings:
        settings['tls'] = {}
        settings['tls']['ca_certs'] = ''

def check_zfs(mount_point):
    for disk in psutil.disk_partitions():
        if disk.mountpoint == mount_point and disk.fstype == 'zfs':
            return True

def add_drives():
    drives = settings['sensors']['external_drives']
    if drives is not None:
        for drive in drives:
            drive_path = settings['sensors']['external_drives'][drive]
            if check_zfs(drive_path):
                usage = get_zpool_use(drive)
                zfs = True
            else:
                usage = get_disk_usage(drive_path)
                zfs = False
            if usage and zfs:
                sensors[f'zpool_use_{drive.lower()}'] = zpool_base(drive)
                # Add drive to list with formatted name, for when checking sensors against settings items
                external_drives.append(f'zpool_use_{drive.lower()}')
            elif usage:
                sensors[f'disk_use_{drive.lower()}'] = external_drive_base(drive, drives[drive])
                # Add drive to list with formatted name, for when checking sensors against settings items
                external_drives.append(f'disk_use_{drive.lower()}')
            else:
                # Skip drives not found. Could be worth sending "not mounted" as the value if users want to track mount status.
                print(drive + ' is not mounted to host. Check config or host drive mount settings.')

# host model method depending on system distro
def get_host_model():
    if "rasp" in OS_DATA["ID"] and isDockerized and isDeviceTreeModel:
        model = subprocess.check_output(["cat", "/app/host/proc/device-tree/model"]).decode("UTF-8").strip()
        # remove a weird character breaking the json in mqtt explorer
        model = model[:-1]
    else:
        # todo find a solid way to determine sbc manufacture
        model = f'{deviceManufacturer} {deviceNameDisplay}'
    return model

def on_connect(client, userdata, flags, reason_code='', properties=''):
    if reason_code == 0:
        write_message_to_console('Connected to broker')
        print("subscribing : " + f"{ha_status}/status")
        client.subscribe(f"{ha_status}/status")
        print("subscribing : " + f"system-sensors/sensor/{devicename}/availability")
        mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'online', retain=True)
        print("subscribing : " + f"system-sensors/sensor/{devicename}/command")
        client.subscribe(f"system-sensors/sensor/{devicename}/command")#subscribe
        client.publish(f"system-sensors/sensor/{devicename}/command", "setup", retain=True)
    elif reason_code == 'Bad user name or password':
        write_message_to_console('Authentication failed.\n Exiting.')
        sys.exit()
    else:
        write_message_to_console('Connection failed')

def on_message(client, userdata, message):
    print (f'Message received: {message.payload.decode()}'  )
    if message.payload.decode() == 'online':
        send_config_message(client)
    elif message.payload.decode() == "display_on":
        reading = subprocess.check_output([vcgencmd, "display_power", "1"]).decode("UTF-8")
        update_sensors()
    elif message.payload.decode() == "display_off":
        reading = subprocess.check_output([vcgencmd, "display_power", "0"]).decode("UTF-8")
        update_sensors()


if __name__ == '__main__':
    try:
        args = _parser().parse_args()
        settings_file = args.settings
    except:
        write_message_to_console('Attempting to find settings file in same folder as ' + str(__file__))
        default_settings_path = str(pathlib.Path(__file__).parent.resolve()) + '/settings.yaml'
        if path.isfile(default_settings_path):
            write_message_to_console('Settings file found, attempting to continue...')
            settings_file = default_settings_path
        else:
            write_message_to_console('Could not find settings.yaml. Please check the documentation')
            exit()

    with open(settings_file) as f:
        settings = yaml.safe_load(f)

    # Make settings file keys all lowercase
    settings = {k.lower(): v for k,v in settings.items()}
    # Prep settings with defaults if keys missingf
    settings = set_defaults(settings)
    # Check for settings that will prevent the script from communicating with MQTT broker or break the script
    check_settings(settings)

    add_drives()

    devicename = settings['devicename'].replace(' ', '').lower()
    deviceNameDisplay = settings['devicename']
    deviceManufacturer = "RPI Foundation" if "rasp" in OS_DATA["ID"] else OS_DATA['NAME']
    deviceModel = get_host_model()
    ha_status = settings['ha_status']
    

    # https://eclipse.dev/paho/files/paho.mqtt.python/html/migrations.html
    # note that with version1, mqttv3 is used and no other migration is made
    # if paho-mqtt v1.6.x gets removed, a full code migration must be made
    if importlib.metadata.version("paho-mqtt")[0] == '1':
       # for paho 1.x clients
       mqttClient = mqtt.Client(client_id=settings['client_id'])
    else:
       # for paho 2.x clients
       # note that a deprecation warning gets logged 
       mqttClient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings['client_id'])

    mqttClient.on_connect = on_connect                      #attach function to callback
    mqttClient.on_message = on_message
    mqttClient.will_set(f'system-sensors/sensor/{devicename}/availability', 'offline', retain=True)
    if 'user' in settings['mqtt']:
        mqttClient.username_pw_set(
            settings['mqtt']['user'], settings['mqtt']['password']
        )

    # if ca_certs is populated, we expect the others have been populated accordingly
    if settings['tls']['ca_certs'] != '':
      mqttClient.tls_set(
        ca_certs=settings['tls']['ca_certs'], certfile=settings['tls']['certfile'], keyfile=settings['tls']['keyfile']
      )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            mqttClient.connect(settings['mqtt']['hostname'], settings['mqtt']['port'])
            break
        except ConnectionRefusedError:
            # sleep for 2 minutes if broker is unavailable and retry.
            # Make this value configurable?
            # this feels like a dirty hack. Is there some other way to do this?
            time.sleep(120)
        except OSError:
            # sleep for 10 minutes if broker is not reachable, i.e. network is down
            # Make this value configurable?
            # this feels like a dirty hack. Is there some other way to do this?
            time.sleep(600)
    try:
        send_config_message(mqttClient)
    except Exception as e:
        write_message_to_console('Error while attempting to send config to MQTT host: ' + str(e))
        exit()
    try:
        update_sensors()
    except Exception as e:
        write_message_to_console('Error while attempting to perform inital sensor update: ' + str(e))
        exit()

    job = Job(interval=dt.timedelta(seconds=poll_interval), execute=update_sensors)
    job.start()

    mqttClient.loop_start()

    while True:
        try:
            sys.stdout.flush()
            time.sleep(1)
        except ProgramKilled:
            write_message_to_console('Program killed: running cleanup code')
            mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'offline', retain=True)
            mqttClient.disconnect()
            mqttClient.loop_stop()
            sys.stdout.flush()
            job.stop()
            break
