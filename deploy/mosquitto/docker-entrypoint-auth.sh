set -eu

if [ -z "${MQTT_USERNAME:-}" ] || [ -z "${MQTT_PASSWORD:-}" ]; then
  echo "MQTT_USERNAME and MQTT_PASSWORD must be set" >&2
  exit 1
fi

mosquitto_passwd -b -c /mosquitto/data/passwords "$MQTT_USERNAME" "$MQTT_PASSWORD"
exec mosquitto -c /mosquitto/config/mosquitto.conf
