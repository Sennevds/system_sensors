# RPI System sensors
I’ve created a simple python script that runs every 60 seconds and sends several system data over MQTT. It uses the MQTT Discovery for Home Assistant so you don’t need to configure anything in Home Assistant if you have discovery enabled for MQTT

It currently logs the following data:
* CPU usage
* CPU temperature
* Disk usage
* Memory usage
* Power status of the RPI
* Last boot
* Last message received timestamp
* Swap usage
* Wifi signal strength
* Amount of upgrades pending
* Disk usage of external drives

# System Requirements

You need to have at least __python 3.6__ installed to use System Sensors.

# Installation:
1. Clone this repo >> git clone https://github.com/Sennevds/system_sensors.git
2. cd system_sensors
3. pip3 install -r requirements.txt
4. sudo apt-get install python3-apt
5. Edit settings_example.yaml in "~/system_sensors/src" to reflect your setup and save as settings.yaml:

| Value  | Required | Default | Description | 
| ------------- | ------------- | ------------- | ------------- |
| hostname  | true | \ | Hostname of the MQTT broker
| port  | false | 1883 | Port of the MQTT broker
| user | false | \ | The userlogin( if defined) for the MQTT broker
| password | false | \ | the password ( if defined) for the MQTT broker
| deviceName | true | \ | device name is sent with topic
| client_id | true | \ | client id to connect to the MQTT broker
| timezone | true | \ | Your local timezone (you can find the list of timezones here: [time zones](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568))
| power_integer_state | false | false | Return the power state in text or integer form
| update_interval | false | 60 | The update interval to send new values to the MQTT broker 
| check_available_updates | false | false | Check the # of avaiblable updates 
| check_wifi_strength | false | false | Check the wifi strength 
| external_drives | false | \ | Declare external drives you want to check disk usage of (see example settings.yaml)

6. python3 system_sensors.py /path/to/settings.yaml
7. (optional) create service to autostart the script at boot:
    1. sudo nano /etc/systemd/system/system_sensors.service
    2. copy following script:
    ```shell
    [Unit]
    Description=System Sensor service
    After=multi-user.target

    [Service]
    User=pi
    Type=idle
    ExecStart=/usr/bin/python3 /home/pi/system_sensors/src/system_sensors.py /home/pi/system_sensors/src/settings.yaml

    [Install]
    WantedBy=multi-user.target
    ```
    3. edit the path to your script path and settings.yaml. Also make sure you replace pi in "User=pi" with the account from which this script will be run. This is typically 'pi' on default raspbian system.
    4. sudo systemctl enable system_sensors.service 
    5. sudo systemctl start system_sensors.service

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
* vertical-stack-in-card
* mini-graph-card
* bar-card

Config:
```yaml
- type: 'custom:vertical-stack-in-card'
    title: Deconz System Monitor
    cards:
      - type: horizontal-stack
        cards:
          - type: custom:mini-graph-card
            entities:
              - sensor.deconzcpuusage
            name: CPU
            line_color: '#2980b9'
            line_width: 2
            hours_to_show: 24
          - type: custom:mini-graph-card
            entities:
              - sensor.deconztemperature
            name: Temp
            line_color: '#2980b9'
            line_width: 2
            hours_to_show: 24
      - type: custom:bar-card
        entity: sensor.deconzdiskuse
        title: HDD
        title_position: inside
        align: split
        show_icon: true
        color: '#00ba6a'
      - type: custom:bar-card
        entity: sensor.deconzmemoryuse
        title: RAM
        title_position: inside
        align: split
        show_icon: true
      - type: entities
        entities:
          - sensor.deconzlastboot
          - sensor.deconzpowerstatus
```
Example:

![alt text](images/example.png?raw=true "Example")
