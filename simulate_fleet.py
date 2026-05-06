#!/usr/bin/env python3
"""
Continuous demo simulator for a fleet of Braga scooters.

Each simulated scooter repeatedly picks one of the Braga datasets, rewrites the
device_id and timestamp, and streams telemetry to the backend by REST or MQTT.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import ssl
import threading
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from import_dataset import (
    DEFAULT_API_URL,
    DEFAULT_DATASET_ROOT,
    Scenario,
    discover_scenarios,
    parse_timestamp,
    read_csv,
    send_rest,
    telemetry_payload,
)


def mqtt_client_from_args(args: argparse.Namespace):
    try:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion
    except ImportError as exc:
        raise RuntimeError("paho-mqtt is required for --mode mqtt. Run: python -m pip install paho-mqtt") from exc

    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    if args.mqtt_username or args.mqtt_password:
        client.username_pw_set(args.mqtt_username, args.mqtt_password)
    if args.mqtt_tls:
        ca_cert = (args.mqtt_ca_cert or "").strip() or None
        if ca_cert:
            client.tls_set(ca_certs=ca_cert, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            client.tls_insecure_set(False)
        else:
            client.tls_set(
                cert_reqs=ssl.CERT_NONE if args.mqtt_tls_insecure else ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
            client.tls_insecure_set(bool(args.mqtt_tls_insecure))
    client.connect(args.mqtt_host, args.mqtt_port, 60)
    client.loop_start()
    return client


def row_delay(previous_row: dict[str, str] | None, row: dict[str, str], speedup: float) -> float:
    if previous_row is None:
        return 0.0
    previous = parse_timestamp(previous_row["timestamp"])
    current = parse_timestamp(row["timestamp"])
    delay = max(0.0, (current - previous).total_seconds())
    return delay / speedup if speedup > 0 else 0.0


def build_payload(row: dict[str, str], device_id: str, scenario_id: str) -> dict[str, Any]:
    payload = telemetry_payload(row)
    payload["device_id"] = device_id
    payload["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    payload["source"] = f"fleet_simulation:{scenario_id}"
    payload["type"] = "telemetry"
    return payload


def send_payload(
    payload: dict[str, Any],
    args: argparse.Namespace,
    mqtt_client,
    mqtt_lock: threading.Lock,
) -> None:
    if args.mode == "rest":
        send_rest(payload, args.api_url, args.api_key, args.timeout)
        return

    topic = f"/bike/{payload['device_id']}/telemetry"
    with mqtt_lock:
        result = mqtt_client.publish(topic, json.dumps(payload), qos=0)
    if result.rc != 0:
        raise RuntimeError(f"MQTT publish failed with rc={result.rc}")


def replay_trip(
    device_id: str,
    scenario: Scenario,
    args: argparse.Namespace,
    stop_event: threading.Event,
    mqtt_client,
    mqtt_lock: threading.Lock,
) -> tuple[int, int]:
    rows = read_csv(scenario.telemetry_path)
    sent = 0
    failed = 0
    previous_row = None

    for row in rows:
        delay = row_delay(previous_row, row, args.speedup)
        if delay > 0 and stop_event.wait(delay):
            break

        payload = build_payload(row, device_id, scenario.scenario_id)
        try:
            send_payload(payload, args, mqtt_client, mqtt_lock)
            sent += 1
        except (RuntimeError, TimeoutError, urllib.error.URLError) as exc:
            failed += 1
            print(f"[WARN] {device_id} {scenario.scenario_id} {row.get('timestamp')}: {exc}", flush=True)
            if args.stop_on_error:
                stop_event.set()
                break

        previous_row = row

    return sent, failed


def choose_scenario(
    scenarios: list[Scenario],
    scooter_index: int,
    trip_index: int,
    selection: str,
    rng: random.Random,
) -> Scenario:
    if selection == "random":
        return rng.choice(scenarios)
    return scenarios[(scooter_index + trip_index) % len(scenarios)]


def scooter_worker(
    scooter_index: int,
    scenarios: list[Scenario],
    args: argparse.Namespace,
    stop_event: threading.Event,
    mqtt_client,
    mqtt_lock: threading.Lock,
) -> None:
    rng = random.Random((args.seed or int(time.time())) + scooter_index)
    device_id = f"{args.device_prefix}{scooter_index + 1:03d}"

    initial_delay = scooter_index * args.start_stagger_sec
    if initial_delay > 0 and stop_event.wait(initial_delay):
        return

    trip_index = 0
    while not stop_event.is_set() and (args.trips_per_scooter == 0 or trip_index < args.trips_per_scooter):
        scenario = choose_scenario(scenarios, scooter_index, trip_index, args.selection, rng)
        print(f"[{device_id}] trip={trip_index + 1} scenario={scenario.scenario_id}", flush=True)
        sent, failed = replay_trip(device_id, scenario, args, stop_event, mqtt_client, mqtt_lock)
        print(f"[{device_id}] finished scenario={scenario.scenario_id} sent={sent} failed={failed}", flush=True)
        trip_index += 1

        if stop_event.is_set() or args.pause_max_sec <= 0:
            continue
        pause = rng.uniform(args.pause_min_sec, args.pause_max_sec)
        stop_event.wait(pause)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a continuous Braga scooter fleet simulation.")
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT), help="Root folder containing Braga scenarios.")
    parser.add_argument("--scenario", action="append", default=[], help="Limit simulation to this scenario. Can be repeated.")
    parser.add_argument("--mode", choices=["mqtt", "rest"], default="mqtt", help="Transport used by simulated scooters.")
    parser.add_argument("--fleet-size", type=int, default=7, help="Number of simulated scooters.")
    parser.add_argument("--device-prefix", default="scooter_demo_", help="Prefix for generated device ids.")
    parser.add_argument("--selection", choices=["round-robin", "random"], default="round-robin", help="How scooters choose datasets.")
    parser.add_argument("--trips-per-scooter", type=int, default=0, help="0 means run until Ctrl+C.")
    parser.add_argument("--speedup", type=float, default=5.0, help="Replay speed multiplier.")
    parser.add_argument("--start-stagger-sec", type=float, default=3.0, help="Delay between scooter starts.")
    parser.add_argument("--pause-min-sec", type=float, default=5.0, help="Minimum pause between trips.")
    parser.add_argument("--pause-max-sec", type=float, default=20.0, help="Maximum pause between trips.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible scenario selection.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop all scooters on the first transport error.")
    parser.add_argument("--api-url", default=os.getenv("IOT_API_URL", DEFAULT_API_URL), help="REST endpoint URL.")
    parser.add_argument("--api-key", default=os.getenv("API_KEY_EDGE") or os.getenv("IOT_API_KEY", "iot"), help="REST API key.")
    parser.add_argument("--timeout", type=float, default=10.0, help="REST request timeout in seconds.")
    parser.add_argument("--mqtt-host", default=os.getenv("MQTT_BROKER", "localhost"), help="MQTT broker host.")
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_HOST_PORT") or os.getenv("MQTT_PORT", "1884")), help="MQTT broker port.")
    parser.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME", "iot"), help="MQTT username.")
    parser.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD", "iot"), help="MQTT password.")
    parser.add_argument("--mqtt-tls", action="store_true", help="Enable MQTT TLS.")
    parser.add_argument("--mqtt-ca-cert", default=os.getenv("MQTT_TLS_CA_CERT", ""), help="Path to CA cert for MQTT TLS.")
    parser.add_argument("--mqtt-tls-insecure", action="store_true", help="Disable MQTT TLS certificate verification.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.fleet_size < 1:
        raise ValueError("--fleet-size must be at least 1")

    scenarios = discover_scenarios(Path(args.dataset_root), args.scenario)
    stop_event = threading.Event()
    mqtt_lock = threading.Lock()
    mqtt_client = mqtt_client_from_args(args) if args.mode == "mqtt" else None

    def request_stop(signum, frame):  # noqa: ARG001
        print("Stopping fleet simulation...", flush=True)
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print(
        f"Starting fleet simulation: scooters={args.fleet_size} scenarios={len(scenarios)} "
        f"mode={args.mode} speedup={args.speedup}",
        flush=True,
    )

    threads = [
        threading.Thread(
            target=scooter_worker,
            args=(index, scenarios, args, stop_event, mqtt_client, mqtt_lock),
            name=f"scooter-{index + 1}",
        )
        for index in range(args.fleet_size)
    ]

    try:
        for thread in threads:
            thread.start()
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.5)
    finally:
        stop_event.set()
        for thread in threads:
            thread.join(timeout=5)
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    main()
