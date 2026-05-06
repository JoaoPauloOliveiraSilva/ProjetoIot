#!/usr/bin/env python3
"""
Smoke test for the local Projeto IoT stack.

It validates:
- backend /health and /health/ready
- dashboard HTTP availability
- REST telemetry ingestion
- MQTT over TLS telemetry (QoS 0) and alert (QoS 1)
- persisted telemetry/alerts via REST queries
- MQTT QoS status endpoint
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


class SmokeTestError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    api_key: str = "",
    timeout: float = 10.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if response.status < 200 or response.status >= 300:
                raise SmokeTestError(f"{method} {url} returned HTTP {response.status}: {body}")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SmokeTestError(f"{method} {url} returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"{method} {url} failed: {exc}") from exc


def request_ok(url: str, *, timeout: float = 10.0) -> None:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status < 200 or response.status >= 300:
                raise SmokeTestError(f"GET {url} returned HTTP {response.status}")
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"GET {url} failed: {exc}") from exc


def api_url(api_base: str, path: str, query: dict[str, Any] | None = None) -> str:
    base = api_base.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


def backend_root(api_base: str) -> str:
    parsed = urllib.parse.urlparse(api_base)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def print_step(message: str) -> None:
    print(f"[smoke] {message}", flush=True)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeTestError(message)


def telemetry_payload(device_id: str, *, source: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "timestamp": now_iso(),
        "source": source,
        "type": "telemetry",
        "lat": 41.5503,
        "lon": -8.4200,
        "speed": 12.4,
        "accel_x": 0.1,
        "accel_y": 0.0,
        "accel_z": 9.8,
        "gyro_x": 0.01,
        "gyro_y": 0.02,
        "gyro_z": 0.01,
        "gps_accuracy_m": 3.5,
        "range_front_m": 4.2,
        "range_left_m": 1.7,
        "ultrasonic_valid": True,
        "battery": 97.0,
    }


def alert_payload(device_id: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "timestamp": now_iso(),
        "source": "smoke_test",
        "type": "alert",
        "event_type": "smoke_test",
        "trigger": "manual_qos1_smoke_test",
        "lat": 41.5503,
        "lon": -8.4200,
        "speed": 0.0,
        "accel_x": 0.0,
        "accel_y": 0.0,
        "accel_z": 9.8,
        "gyro_x": 0.0,
        "gyro_y": 0.0,
        "gyro_z": 0.0,
        "range_front_m": 1.0,
        "range_left_m": 1.0,
        "ultrasonic_valid": True,
    }


def export_ca_cert(ca_cert: Path, container: str, no_export_ca: bool) -> None:
    if no_export_ca:
        assert_true(ca_cert.exists(), f"CA cert not found: {ca_cert}")
        return

    ca_cert.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["docker", "cp", f"{container}:/mosquitto/data/tls/ca.crt", str(ca_cert)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print_step(f"CA certificate ready: {ca_cert}")
        return

    if ca_cert.exists():
        print_step(f"Could not refresh CA from Docker; using existing file: {ca_cert}")
        return

    details = (result.stderr or result.stdout or "").strip()
    raise SmokeTestError(f"Could not export CA cert from container {container}: {details}")


def publish_mqtt(args: argparse.Namespace, device_id: str) -> None:
    try:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion
    except ImportError as exc:
        raise SmokeTestError("paho-mqtt is required. Run: python -m pip install paho-mqtt") from exc

    ca_cert = Path(args.mqtt_ca_cert).resolve()
    export_ca_cert(ca_cert, args.mqtt_container, args.no_export_ca)

    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    client.username_pw_set(args.mqtt_username, args.mqtt_password)
    client.tls_set(ca_certs=str(ca_cert), cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(False)

    rc = client.connect(args.mqtt_host, args.mqtt_port, 60)
    if rc != 0:
        raise SmokeTestError(f"MQTT connect failed with rc={rc}")

    client.loop_start()
    try:
        telemetry = telemetry_payload(device_id, source="smoke_test_mqtt")
        telemetry_info = client.publish(f"/bike/{device_id}/telemetry", json.dumps(telemetry), qos=0)
        telemetry_info.wait_for_publish(timeout=args.timeout)
        if telemetry_info.rc != 0:
            raise SmokeTestError(f"MQTT telemetry publish failed with rc={telemetry_info.rc}")

        alert = alert_payload(device_id)
        alert_info = client.publish(f"/bike/{device_id}/alert", json.dumps(alert), qos=1)
        alert_info.wait_for_publish(timeout=args.timeout)
        if alert_info.rc != 0:
            raise SmokeTestError(f"MQTT alert publish failed with rc={alert_info.rc}")
    finally:
        client.loop_stop()
        client.disconnect()


def wait_for_records(
    args: argparse.Namespace,
    *,
    path: str,
    query: dict[str, Any],
    expected_min: int = 1,
    label: str,
) -> dict[str, Any]:
    deadline = time.time() + args.wait_timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = request_json(api_url(args.api_base, path, query), api_key=args.api_key, timeout=args.timeout)
        if int(last.get("total_registos") or 0) >= expected_min:
            return last
        time.sleep(args.poll_interval)
    raise SmokeTestError(f"Timed out waiting for {label}. Last response: {last}")


def run(args: argparse.Namespace) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    rest_device_id = f"smoke_rest_{stamp}"
    mqtt_device_id = f"smoke_mqtt_{stamp}"
    root = backend_root(args.api_base)

    print_step("checking backend health")
    health = request_json(f"{root}/health", timeout=args.timeout)
    assert_true(health.get("status") == "ok", f"Unexpected /health response: {health}")

    print_step("checking backend readiness")
    ready = request_json(f"{root}/health/ready", timeout=args.timeout)
    assert_true(ready.get("status") == "ready", f"Unexpected /health/ready response: {ready}")

    print_step("checking dashboard")
    request_ok(args.dashboard_url, timeout=args.timeout)

    print_step("posting REST telemetry")
    rest_payload = telemetry_payload(rest_device_id, source="smoke_test_rest")
    request_json(
        api_url(args.api_base, "/sensors"),
        method="POST",
        payload=rest_payload,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    print_step("checking persisted REST telemetry")
    wait_for_records(
        args,
        path="/sensors",
        query={"minutos": 5, "device_id": rest_device_id},
        label="REST telemetry",
    )

    if not args.skip_mqtt:
        print_step("publishing MQTT TLS telemetry QoS 0 and alert QoS 1")
        publish_mqtt(args, mqtt_device_id)

        print_step("checking persisted MQTT telemetry")
        wait_for_records(
            args,
            path="/sensors",
            query={"minutos": 5, "device_id": mqtt_device_id},
            label="MQTT telemetry",
        )

        print_step("checking persisted MQTT QoS 1 alert")
        wait_for_records(
            args,
            path="/alerts",
            query={"minutos": 5, "device_id": mqtt_device_id, "event_type": "smoke_test"},
            label="MQTT alert",
        )

        print_step("checking QoS status")
        qos_response = request_json(api_url(args.api_base, "/qos/status"), api_key=args.api_key, timeout=args.timeout)
        qos = qos_response.get("qos") or {}
        assert_true(bool(qos.get("connected")), f"MQTT subscriber is not connected: {qos}")
        assert_true(int(qos.get("processed_qos0") or 0) >= 1, f"QoS 0 was not processed: {qos}")
        assert_true(int(qos.get("processed_qos1") or 0) >= 1, f"QoS 1 was not processed: {qos}")

    print_step("PASS stack smoke test completed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test the local Projeto IoT stack.")
    parser.add_argument("--api-base", default=os.getenv("IOT_API_BASE_URL", "http://localhost:8000/api/v1"))
    parser.add_argument("--dashboard-url", default=os.getenv("IOT_DASHBOARD_URL", "http://localhost:8080/?api_key=iot"))
    parser.add_argument("--api-key", default=os.getenv("API_KEY_EDGE") or os.getenv("IOT_API_KEY", "iot"))
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--wait-timeout", type=float, default=20.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--skip-mqtt", action="store_true")
    parser.add_argument("--mqtt-host", default=os.getenv("MQTT_BROKER", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_HOST_PORT") or os.getenv("MQTT_PORT", "8883")))
    parser.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME", "iot"))
    parser.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD", "iot"))
    parser.add_argument("--mqtt-ca-cert", default=str(REPO_ROOT / "mosquitto-ca.crt"))
    parser.add_argument("--mqtt-container", default="iot-mosquitto")
    parser.add_argument("--no-export-ca", action="store_true", help="Use --mqtt-ca-cert as-is instead of docker cp from the Mosquitto container.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        run(args)
    except SmokeTestError as exc:
        print(f"[smoke] FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
