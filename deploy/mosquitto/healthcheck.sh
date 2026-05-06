#!/bin/sh
set -eu

mosquitto_sub \
  -h localhost \
  -p 8883 \
  -u "$MQTT_USERNAME" \
  -P "$MQTT_PASSWORD" \
  --cafile /mosquitto/data/tls/ca.crt \
  --tls-version tlsv1.2 \
  -t '$SYS/broker/uptime' \
  -C 1 \
  -W 3 >/dev/null
