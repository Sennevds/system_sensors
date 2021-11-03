
# System Requirements


Proxmox 7 pve

# Changes / Automatic

- Create Group/User systemsensors ( linux )
- Autodetect timezone ( linux )
- Last message disabled ( config )
- Wifi ( config )

## Install:


```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/patriciocl/system_sensors/master/contrib/install_proxmox.sh USERMQTT PASSMQTT HOSTMQTT)"
```

## Example:
```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/patriciocl/system_sensors/master/contrib/install_proxmox.sh patriciomqtt Superpass 192.168.97.21)"
```
