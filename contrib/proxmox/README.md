
# System Requirements


Proxmox 7 pve

# Changes / Automatic

- Create Group/User systemsensors ( linux )
- Autodetect timezone ( linux )
- Last message disabled ( config )
- Wifi ( config )

## Install:


```bash
wget -qO install_proxmox.sh https://raw.githubusercontent.com/Sennevds/system_sensors/master/contrib/proxmox/install_proxmox.sh
sh install_proxmox.sh USERMQTT PASSMQTT HOSTMQTT DEVICENAME
```

Example:

```bash
wget -qO install_proxmox.sh https://raw.githubusercontent.com/Sennevds/system_sensors/master/contrib/proxmox/install_proxmox.sh
sh install_proxmox.sh hass hass 192.168.98.21 Proxmox
```
