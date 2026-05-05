set -eu

mosquitto_sub \
  -h localhost \
  -p 1883 \
  -u "$MQTT_USERNAME" \
  -P "$MQTT_PASSWORD" \
  -t '$SYS/broker/uptime' \
  -C 1 \
  -W 3 >/dev/null
