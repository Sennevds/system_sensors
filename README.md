# RPI System sensors

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE.md)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

[![Community Forum][forum-shield]][forum]

I’ve created a simple python script that runs every 60 seconds and sends several system data over MQTT. It uses the MQTT Discovery for Home Assistant so you don’t need to configure anything in Home Assistant if you have discovery enabled for MQTT

It currently logs the following data:

- CPU usage
- CPU temperature
- CPU Clock Speed
- Disk usage
- Memory usage
- Power status of the RPI
- Last boot
- Last message received timestamp
- Swap usage
- Wifi signal strength
- Wifi connected SSID
- Amount of upgrades pending
- Disk usage of external drives
- Hostname
- Host local IP
- Host OS distro and version
- CPU Load (1min, 5min and 15min)
- Network Download & Upload throughput

# System Requirements

You need to have at least **python 3.6** installed to use System Sensors.

# Installation:

1. Clone this repo >> git clone https://github.com/Sennevds/system_sensors.git
2. `cd system_sensors`
3. `sudo apt-get install python3-dev`
4. `sudo apt-get install python3-apt`
5. `pip3 install -r requirements.txt`
6. Edit settings_example.yaml in "~/system_sensors/src" to reflect your setup and save as settings.yaml:

| Value                           | Required | Default | Description                                                                                                                                     |
| ------------------------------- | -------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| mqtt                            | true     | \       | Details of the MQTT broker                                                                                                                      |
| mqtt:hostname                   | true     | \       | Hostname of the MQTT broker                                                                                                                     |
| mqtt:port                       | false    | 1883    | Port of the MQTT broker                                                                                                                         |
| mqtt:user                       | false    | \       | The userlogin( if defined) for the MQTT broker                                                                                                  |
| mqtt:password                   | false    | \       | the password ( if defined) for the MQTT broker                                                                                                  |
| deviceName                      | true     | \       | device name is sent with topic                                                                                                                  |
| client_id                       | true     | \       | client id to connect to the MQTT broker                                                                                                         |
| timezone                        | true     | \       | Your local timezone (you can find the list of timezones here: [time zones](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568)) |
| power_integer_state(Deprecated) | false    | false   | Deprecated                                                                                                                                      |
| update_interval                 | false    | 60      | The update interval to send new values to the MQTT broker                                                                                       |
| sensors                         | false    | \       | Enable/disable individual sensors (see example settings.yaml for how-to). Default is true for all sensors.                                      |

7. `python3 src/system_sensors.py src/settings.yaml`
8. (optional) create a service to autostart the script at boot, copy  the content of the `example_system_sensors.service` file into the editor:
   1. `sudo systemctl edit --force --full system.sensors`
   2. edit the path to your script path and settings.yaml. Also make sure you replace pi in "User=pi" with the account from which this script will be run. This is typically 'pi' on default raspbian system.
   3. `sudo systemctl daemon-reload`
   4. `sudo systemctl enable --now system.sensors.service`
   5. `sudo systemctl status system.sensors.service`
   
# Docker 
## Preparations
Before running this application in a docker container you'll need to add the following to the crontab
```
@reboot <git clone location>/src/bin/ip_pipe.sh
```
This little script will create a pipe and fetch the Host OS IP address and put it in the pipe.  
The container will have the pipe mounted `/tmp/system_sensor_pipe:/app/host/system_sensor_pipe:ro` so it can read the ip.  
this is required sinds docker container can't and *shouldn't* access the host OS

## Start Container
Running in docker container is very symplistic:
```
docker-compose up -d
```

# Home Assistant configuration:

## Configuration:

The only config you need in Home Assistant is the following:

```yaml
mqtt:
  discovery: true
  discovery_prefix: homeassistant
```

## Lovelace UI example:

I have used following custom plugins for lovelace:

- vertical-stack-in-card
- mini-graph-card
- bar-card

Config:

```yaml
type: custom:vertical-stack-in-card
title: Deconz System Monitor
cards:
  - type: horizontal-stack
    cards:
      - type: custom:mini-graph-card
        entities:
          - sensor.deconz_cpu_usage
        name: CPU
        line_color: '#2980b9'
        line_width: 2
        hours_to_show: 24
      - type: custom:mini-graph-card
        entities:
          - sensor.deconz_temperature
        name: Temp
        line_color: '#2980b9'
        line_width: 2
        hours_to_show: 24
  - type: custom:bar-card
    entity: sensor.deconz_disk_use
    name: HDD
    positions:
      icon: outside
      name: inside
    color: '#00ba6a'
  - type: custom:bar-card
    entity: sensor.deconz_memory_use
    name: RAM
    positions:
      icon: outside
      name: inside
  - type: entities
    entities:
      - sensor.deconz_last_boot
      - binary_sensor.deconz_under_voltage
```

Note: you need to change the friendly name for entities like last boot in the _entity settings_, the card  prints the default entity string if no friendly name was defined.

Example:

![alt text](images/example.png?raw=true "Example")

[commits-shield]: https://img.shields.io/github/commit-activity/y/Sennevds/system_sensors?style=for-the-badge
[commits]: https://github.com/sennevds/system_sensors/commits/master
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/t/remote-rpi-system-monitor/129274
[license-shield]: https://img.shields.io/github/license/sennevds/system_sensors.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/maintenance/yes/2020.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/sennevds/system_sensors.svg?style=for-the-badge
[releases]: https://github.com/sennevds/system_sensors/releases
