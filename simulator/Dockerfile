FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY import_dataset.py simulate_fleet.py ./
COPY datasets ./datasets

CMD ["python", "simulate_fleet.py", "--mode", "mqtt", "--mqtt-host", "mosquitto", "--mqtt-port", "8883", "--mqtt-tls", "--mqtt-ca-cert", "/mosquitto-data/tls/ca.crt", "--fleet-size", "16", "--speedup", "5", "--selection", "random", "--publish-truth-alerts", "--dock-verify-api-url", "http://backend:8000/api/v1/sensors"]
