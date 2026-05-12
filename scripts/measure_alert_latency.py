#!/usr/bin/env python3
"""
Measure end-to-end alert latency through the REST ingestion path.

The script posts one telemetry sample that must trigger a hard_brake alert,
then polls the alerts endpoint until that alert is visible in InfluxDB.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def request_json(url: str, *, api_key: str = "", payload: dict | None = None, timeout: float = 5.0) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    method = "POST" if payload is not None else "GET"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure REST telemetry to persisted alert latency.")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1", help="Backend API base URL.")
    parser.add_argument("--api-key", default="iot", help="API key sent as X-API-Key.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Maximum seconds to wait for the alert.")
    parser.add_argument("--poll-interval", type=float, default=0.1, help="Seconds between alert polls.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    device_id = f"latency_test_{int(time.time() * 1000)}"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    telemetry = {
        "device_id": device_id,
        "source": "latency_test",
        "type": "telemetry",
        "timestamp": timestamp,
        "lat": 41.5503,
        "lon": -8.4200,
        "speed": 14.0,
        "accel_x": 0.1,
        "accel_y": -7.4,
        "accel_z": 9.7,
        "gyro_x": 0.0,
        "gyro_y": 0.0,
        "gyro_z": 0.0,
        "range_front_m": 3.2,
        "range_left_m": 1.1,
        "ultrasonic_valid": True,
        "battery": 92.0,
    }

    sensors_url = f"{args.api_base.rstrip('/')}/sensors"
    alerts_url = (
        f"{args.api_base.rstrip('/')}/alerts?"
        + urllib.parse.urlencode({"minutos": 5, "device_id": device_id, "event_type": "hard_brake"})
    )

    start = time.perf_counter()
    request_json(sensors_url, api_key=args.api_key, payload=telemetry, timeout=args.timeout)

    deadline = start + args.timeout
    while time.perf_counter() < deadline:
        response = request_json(alerts_url, api_key=args.api_key, timeout=args.timeout)
        alerts = response.get("dados") or []
        if alerts:
            latency_ms = (time.perf_counter() - start) * 1000.0
            print(f"PASS alert latency: {latency_ms:.1f} ms")
            print(f"device_id={device_id} event_type={alerts[0].get('event_type')}")
            return
        time.sleep(args.poll_interval)

    raise SystemExit(f"FAIL alert not visible after {args.timeout:.1f}s for device_id={device_id}")


if __name__ == "__main__":
    main()
