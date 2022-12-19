#!/bin/bash

############################################
### https://stackoverflow.com/a/63719458 ###
############################################

if [ ! -p "/tmp/system_sensor_pipe" ]; then
    mkfifo "/tmp/system_sensor_pipe"
fi

while true; do cat /proc/net/tcp > "/tmp/system_sensor_pipe"; sleep 0.5; done;
#while true; do hostname -I > "/tmp/system_sensor_pipe"; sleep 0.5; done;