set -eu

if [ -z "${MQTT_USERNAME:-}" ] || [ -z "${MQTT_PASSWORD:-}" ]; then
  echo "MQTT_USERNAME and MQTT_PASSWORD must be set" >&2
  exit 1
fi

TLS_DIR=/mosquitto/data/tls
mkdir -p "$TLS_DIR"

if [ ! -f "$TLS_DIR/ca.crt" ] || [ ! -f "$TLS_DIR/ca.key" ] || [ ! -f "$TLS_DIR/server.crt" ] || [ ! -f "$TLS_DIR/server.key" ]; then
  openssl genrsa -out "$TLS_DIR/ca.key" 2048
  openssl req -x509 -new -nodes -key "$TLS_DIR/ca.key" -sha256 -days 3650 -subj "/CN=iot-mosquitto-ca" -out "$TLS_DIR/ca.crt"

  openssl genrsa -out "$TLS_DIR/server.key" 2048
  openssl req -new -key "$TLS_DIR/server.key" -subj "/CN=mosquitto" -addext "subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1" -out "$TLS_DIR/server.csr"
  openssl x509 -req -in "$TLS_DIR/server.csr" -CA "$TLS_DIR/ca.crt" -CAkey "$TLS_DIR/ca.key" -CAcreateserial -out "$TLS_DIR/server.crt" -days 3650 -sha256 -copy_extensions copy
  rm -f "$TLS_DIR/server.csr" "$TLS_DIR/ca.srl"

  chmod 0644 "$TLS_DIR/ca.crt" "$TLS_DIR/server.crt"
  chmod 0600 "$TLS_DIR/ca.key" "$TLS_DIR/server.key"
fi

rm -f /tmp/mosquitto-passwords
mosquitto_passwd -b -c /tmp/mosquitto-passwords "$MQTT_USERNAME" "$MQTT_PASSWORD"
chmod 0700 /tmp/mosquitto-passwords
chown mosquitto:mosquitto /tmp/mosquitto-passwords || true
exec mosquitto -c /mosquitto/config/mosquitto.conf
