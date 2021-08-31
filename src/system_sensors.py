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

from sensors import * 


mqttClient = None
global poll_interval
devicename = None
settings = {}

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
        # skip sensors that have been disabled
        if settings['sensors'][sensor] == False:
            continue
        payload_str += f'"{sensor}": "{attr["function"]()}",'
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
            if settings['sensors'][sensor]:
                mqttClient.publish(
                    topic=f'homeassistant/{attr["sensor_type"]}/{devicename}/{sensor}/config',
                    payload = (f'{{'
                            + (f'"device_class":"{attr["class"]}",' if 'class' in attr else '')
                            + f'"name":"{deviceNameDisplay} {attr["name"]}",'
                            + f'"state_topic":"system-sensors/sensor/{devicename}/state",'
                            + (f'"unit_of_measurement":"{attr["unit"]}",' if 'unit' in attr else '')
                            + f'"value_template":"{{{{value_json.{sensor}}}}}",'
                            + f'"unique_id":"{devicename}_sensor_{sensor}",'
                            + f'"availability_topic":"system-sensors/sensor/{devicename}/availability",'
                            + f'"device":{{"identifiers":["{devicename}_sensor"],'
                            + f'"name":"{deviceNameDisplay} Sensors","model":"RPI {deviceNameDisplay}", "manufacturer":"RPI"}}'
                            + (f',"icon":"mdi:{attr["icon"]}"' if 'icon' in attr else '')
                            + f'}}'
                            ),
                    qos=1,
                    retain=True,
                )
        except Exception as e:
            print('An error was produced while processing ' + str(sensor) + ' with exception: ' + str(e))
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

    # 'settings' argument is local, so this updated version needs to be returned to overwrite the one in the main function
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

def add_drives():
    drives = settings['sensors']['external_drives']
    if drives is not None:
        for drive in drives:
            # check if drives exist?
            sensors[f'disk_use_{drive.lower()}'] = {
                        'name': f'Disk Use {drive}',
                        'unit': '%',
                        'icon': 'harddisk'
                        }

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        write_message_to_console('Connected to broker')
        client.subscribe('hass/status')
        mqttClient.publish(f'system-sensors/sensor/{devicename}/availability', 'online', retain=True)
    elif rc == 5:
        write_message_to_console('Authentication failed.\n Exiting.')
        sys.exit()
    else:
        write_message_to_console('Connection failed')

def on_message(client, userdata, message):
    print (f'Message received: {message.payload.decode()}'  )
    if(message.payload.decode() == 'online'):
        send_config_message(client)


if __name__ == '__main__':
    try:
        args = _parser().parse_args()
        settings_file = args.settings
    except:
        print('Attempting to find settings file in same folder as ' + str(__file__))
        default_settings_path = str(pathlib.Path(__file__).parent.resolve()) + '/settings.yaml'
        if path.isfile(default_settings_path):
            print('Settings file found, attempting to continue...')
            settings_file = default_settings_path
        else:
            print('Could not find settings.yaml. Please check the documentation')
            exit()

    with open(settings_file) as f:
        settings = yaml.safe_load(f)

    # Make settings file keys all lowercase
    settings = {k.lower(): v for k,v in settings.items()}
    # Prep settings with defaults if keys missing
    settings = set_defaults(settings)
    # Check for settings that will prevent the script from communicating with MQTT broker or break the script
    check_settings(settings)
    
    add_drives()

    devicename = settings['devicename'].replace(' ', '').lower()
    deviceNameDisplay = settings['devicename']

    mqttClient = mqtt.Client(client_id=settings['client_id'])
    mqttClient.on_connect = on_connect                      #attach function to callback
    mqttClient.on_message = on_message
    mqttClient.will_set(f'system-sensors/sensor/{devicename}/availability', 'offline', retain=True)
    if 'user' in settings['mqtt']:
        mqttClient.username_pw_set(
            settings['mqtt']['user'], settings['mqtt']['password']
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
