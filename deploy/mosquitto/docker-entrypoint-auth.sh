set -eu

if [ -z "${MQTT_USERNAME:-}" ] || [ -z "${MQTT_PASSWORD:-}" ]; then
  echo "MQTT_USERNAME and MQTT_PASSWORD must be set" >&2
  exit 1
fi

rm -f /tmp/mosquitto-passwords
mosquitto_passwd -b -c /tmp/mosquitto-passwords "$MQTT_USERNAME" "$MQTT_PASSWORD"
chmod 0644 /tmp/mosquitto-passwords
exec mosquitto -c /mosquitto/config/mosquitto.conf
