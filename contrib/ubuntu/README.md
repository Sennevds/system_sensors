# Ubuntu Install Script

## System Requirements

Ubuntu Linux (may also work on other debian based distros)

## Steps

- Creates system user
- Install dependencies
- Generate config file
- Setup as a service

## Install

```bash
curl -o install-systemsensors.sh https://raw.githubusercontent.com/benmepham/system_sensors/master/contrib/ubuntu/install.sh
# Please inspect and edit the script before running
sudo bash install-systemsensors.sh MQTT_USER MQTT_HOST
```

Example:

```bash
curl -o install-systemsensors.sh https://raw.githubusercontent.com/benmepham/system_sensors/master/contrib/ubuntu/install.sh
sudo bash install-systemsensors.sh hass 192.168.98.21
```

## Update

(retains settings while pulling new files and installing updates)

```bash
curl -o update-systemsensors.sh https://raw.githubusercontent.com/benmepham/system_sensors/ubuntu-script/contrib/ubuntu/update.sh
# Please inspect and edit the script before running
sudo bash update-systemsensors.sh
```

## Uninstall

todo
