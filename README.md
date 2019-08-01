# RPI System sensors
I’ve created a simple python script that runs every 60 seconds and sends several system data over MQTT. It uses the MQTT Discovery for Home Assistant so you don’t need to configure anything in Home Assistant if you have discovery enabled for MQTT

It currently logs the following data:
* CPU usage
* CPU temperature
* Disk usage
* Memory usage
* Power status of the RPI
* Last boot

# Installation:
1. Clone this repo
2. cd system_sensors
3. pip install -r requirements.txt
4. python system_sensors.py
5. (optional) create service to autostart the script at boot:
    1. sudo nano /etc/systemd/system/system_sensor.service
    2. copy following script:
    ```shell
    [Unit]
    Description=System Sensor service
    After=multi-user.target

    [Service]
    Type=idle
    ExecStart=/usr/bin/python3 /home/pi/sensors/system_sensors.py

    [Install]
    WantedBy=multi-user.target
    ```
    3. edit the path to your script path
    4. sudo systemctl enable system_sensor.service 
    5. sudo systemctl start system_sensor.service

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
