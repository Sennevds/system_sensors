


# check if settings.yaml exists
if [ ! -f "/app/config/config.yaml" ]; then
    cat /app/settings_example.yaml > /app/config/config.yaml
fi

# if not then copy the default
python /app/system_sensors.py /app/config/config.yaml