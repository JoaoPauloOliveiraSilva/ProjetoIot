#!/usr/bin/env python3
"""
Generate synthetic scooter telemetry datasets on real Braga streets.

The generator fetches Braga road/cycleway geometry from OpenStreetMap through
Overpass, builds a lightweight routing graph, then creates deterministic
normal and incident trajectories with GPS, IMU, and ultrasonic readings.
"""

from __future__ import annotations

import csv
import heapq
import json
import math
import random
import shutil
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "datasets" / "braga"
CACHE_DIR = OUTPUT_ROOT / "_cache"
OSM_CACHE_PATH = CACHE_DIR / "braga_highways_overpass.json"

# Bounding box around Braga city, Portugal: south, west, north, east.
BRAGA_BBOX = (41.5200, -8.4700, 41.5900, -8.3500)

HIGHWAY_WHITELIST = {
    "cycleway",
    "living_street",
    "pedestrian",
    "primary",
    "residential",
    "secondary",
    "service",
    "tertiary",
    "unclassified",
}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

CSV_COLUMNS = [
    "scenario_id",
    "device_id",
    "timestamp",
    "source",
    "type",
    "lat",
    "lon",
    "speed",
    "accel_x",
    "accel_y",
    "accel_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "gps_accuracy_m",
    "range_front_m",
    "range_left_m",
    "ultrasonic_valid",
    "battery",
    "event_label",
]


@dataclass(frozen=True)
class Node:
    lat: float
    lon: float


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    event_type: str | None
    min_route_m: float
    max_route_m: float
    base_speed_kmh: float
    device_id: str
    description: str


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def overpass_query() -> str:
    south, west, north, east = BRAGA_BBOX
    highway_regex = "|".join(sorted(HIGHWAY_WHITELIST))
    return f"""
    [out:json][timeout:120];
    (
      way["highway"~"^({highway_regex})$"]({south},{west},{north},{east});
    );
    (._;>;);
    out body;
    """


def fetch_osm_data(force: bool = False) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if OSM_CACHE_PATH.exists() and not force:
        return json.loads(OSM_CACHE_PATH.read_text(encoding="utf-8"))

    encoded = urllib.parse.urlencode({"data": overpass_query()}).encode("utf-8")
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        request = urllib.request.Request(
            endpoint,
            data=encoded,
            headers={"User-Agent": "ProjetoIot-BragaDatasetGenerator/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            OSM_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as exc:  # pragma: no cover - defensive network fallback
            last_error = exc
            time.sleep(2)

    raise RuntimeError(f"Could not fetch OpenStreetMap data: {last_error}")


def build_graph(osm_data: dict[str, Any]) -> tuple[dict[int, Node], dict[int, list[tuple[int, float]]]]:
    nodes: dict[int, Node] = {}
    ways: list[dict[str, Any]] = []

    for element in osm_data.get("elements", []):
        if element.get("type") == "node":
            nodes[int(element["id"])] = Node(lat=float(element["lat"]), lon=float(element["lon"]))
        elif element.get("type") == "way":
            tags = element.get("tags", {})
            if tags.get("highway") in HIGHWAY_WHITELIST:
                ways.append(element)

    graph: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for way in ways:
        way_nodes = [int(node_id) for node_id in way.get("nodes", []) if int(node_id) in nodes]
        for left, right in zip(way_nodes, way_nodes[1:]):
            a = nodes[left]
            b = nodes[right]
            distance = haversine_m(a.lat, a.lon, b.lat, b.lon)
            if distance <= 0:
                continue
            graph[left].append((right, distance))
            graph[right].append((left, distance))

    return nodes, graph


def largest_component(graph: dict[int, list[tuple[int, float]]]) -> set[int]:
    seen: set[int] = set()
    largest: set[int] = set()

    for start in graph:
        if start in seen:
            continue
        component: set[int] = set()
        queue = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            component.add(node)
            for neighbor, _ in graph[node]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        if len(component) > len(largest):
            largest = component

    return largest


def shortest_path(
    graph: dict[int, list[tuple[int, float]]],
    start: int,
    end: int,
) -> tuple[list[int], float] | None:
    distances: dict[int, float] = {start: 0.0}
    previous: dict[int, int] = {}
    heap: list[tuple[float, int]] = [(0.0, start)]

    while heap:
        distance, node = heapq.heappop(heap)
        if node == end:
            break
        if distance > distances.get(node, math.inf):
            continue
        for neighbor, edge_length in graph[node]:
            candidate = distance + edge_length
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(heap, (candidate, neighbor))

    if end not in distances:
        return None

    path = [end]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return path, distances[end]


def choose_route(
    graph: dict[int, list[tuple[int, float]]],
    component: set[int],
    rng: random.Random,
    min_m: float,
    max_m: float,
) -> tuple[list[int], float]:
    candidates = list(component)
    for _ in range(600):
        start, end = rng.sample(candidates, 2)
        result = shortest_path(graph, start, end)
        if not result:
            continue
        path, length_m = result
        if min_m <= length_m <= max_m and len(path) >= 8:
            return path, length_m
    raise RuntimeError(f"Could not find route between {min_m:.0f}m and {max_m:.0f}m")


def route_coordinates(nodes: dict[int, Node], route: list[int]) -> list[tuple[float, float]]:
    return [(nodes[node_id].lat, nodes[node_id].lon) for node_id in route]


def route_length(points: list[tuple[float, float]]) -> float:
    return sum(
        haversine_m(a[0], a[1], b[0], b[1])
        for a, b in zip(points, points[1:])
    )


def interpolate_at(points: list[tuple[float, float]], target_m: float) -> tuple[float, float]:
    if target_m <= 0:
        return points[0]

    covered = 0.0
    for start, end in zip(points, points[1:]):
        segment = haversine_m(start[0], start[1], end[0], end[1])
        if covered + segment >= target_m:
            ratio = 0.0 if segment == 0 else (target_m - covered) / segment
            lat = start[0] + (end[0] - start[0]) * ratio
            lon = start[1] + (end[1] - start[1]) * ratio
            return lat, lon
        covered += segment

    return points[-1]


def event_window(event_type: str | None, estimated_duration_s: int) -> dict[str, int]:
    if event_type == "hard_brake":
        start = max(20, int(estimated_duration_s * 0.45))
        return {"start": start, "end": start + 5}
    if event_type == "fall_accident":
        start = max(20, int(estimated_duration_s * 0.55))
        return {"start": start, "end": start + 30}
    if event_type == "traffic_jam":
        start = max(25, int(estimated_duration_s * 0.35))
        return {"start": start, "end": start + 95}
    if event_type == "mixed":
        start = max(25, int(estimated_duration_s * 0.30))
        return {"brake_start": start, "brake_end": start + 5, "jam_start": start + 30, "jam_end": start + 120}
    return {}


def speed_for_second(
    spec: ScenarioSpec,
    t: int,
    window: dict[str, int],
    rng: random.Random,
) -> float:
    base = max(0.0, rng.gauss(spec.base_speed_kmh, 1.6))

    if spec.event_type is None:
        if spec.scenario_id == "normal_stop_and_go_001" and (55 <= t <= 68 or 145 <= t <= 158):
            return max(0.0, rng.gauss(0.8, 0.4))
        if spec.scenario_id == "normal_rough_pavement_001":
            return max(4.0, rng.gauss(spec.base_speed_kmh - 2.0, 2.4))
        return max(5.0, min(25.0, base))

    if spec.event_type == "hard_brake":
        if t < window["start"]:
            return max(12.0, min(28.0, base + 3.0))
        if window["start"] <= t <= window["end"]:
            return max(1.0, 22.0 - (t - window["start"] + 1) * 4.5)
        return max(4.0, rng.gauss(9.0, 2.0))

    if spec.event_type == "fall_accident":
        if t < window["start"]:
            return max(8.0, min(24.0, base))
        return 0.0

    if spec.event_type == "traffic_jam":
        if window["start"] <= t <= window["end"]:
            return max(0.2, rng.gauss(1.1, 0.25))
        return max(6.0, min(20.0, base))

    if spec.event_type == "mixed":
        if window["brake_start"] <= t <= window["brake_end"]:
            return max(1.0, 21.0 - (t - window["brake_start"] + 1) * 4.2)
        if window["jam_start"] <= t <= window["jam_end"]:
            return max(0.2, rng.gauss(1.0, 0.25))
        return max(6.0, min(23.0, base))

    return max(5.0, min(25.0, base))


def event_label_for_second(spec: ScenarioSpec, t: int, window: dict[str, int]) -> str:
    if spec.event_type == "hard_brake" and window["start"] <= t <= window["end"]:
        return "hard_brake"
    if spec.event_type == "fall_accident" and t == window["start"]:
        return "fall_accident"
    if spec.event_type == "traffic_jam" and window["start"] <= t <= window["end"]:
        return "traffic_jam"
    if spec.event_type == "mixed":
        if window["brake_start"] <= t <= window["brake_end"]:
            return "hard_brake"
        if window["jam_start"] <= t <= window["jam_end"]:
            return "traffic_jam"
    return ""


def generate_rows(
    spec: ScenarioSpec,
    points: list[tuple[float, float]],
    rng: random.Random,
    start_time: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    length_m = route_length(points)
    estimated_duration_s = max(60, int(length_m / (spec.base_speed_kmh / 3.6)))
    window = event_window(spec.event_type, estimated_duration_s)

    rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    covered_m = 0.0
    prev_speed_mps = spec.base_speed_kmh / 3.6
    battery = rng.uniform(87.0, 99.0)
    max_seconds = estimated_duration_s + 180

    for t in range(max_seconds):
        speed_kmh = speed_for_second(spec, t, window, rng)
        speed_mps = speed_kmh / 3.6
        covered_m = min(length_m, covered_m + speed_mps)
        lat, lon = interpolate_at(points, covered_m)
        timestamp = start_time + timedelta(seconds=t)
        label = event_label_for_second(spec, t, window)

        accel_y = (speed_mps - prev_speed_mps) + rng.gauss(0.0, 0.18)
        accel_x = rng.gauss(0.0, 0.35)
        accel_z = rng.gauss(9.81, 0.22)
        gyro_x = rng.gauss(0.0, 0.035)
        gyro_y = rng.gauss(0.0, 0.035)
        gyro_z = rng.gauss(0.0, 0.05)
        range_front = rng.uniform(2.2, 9.5)
        range_left = rng.uniform(0.7, 2.8)

        if spec.scenario_id == "normal_rough_pavement_001" and t % 37 in {0, 1}:
            accel_x += rng.uniform(1.4, 2.2)
            accel_z += rng.uniform(2.0, 4.2)
            gyro_z += rng.uniform(0.25, 0.45)

        if label == "hard_brake":
            accel_y = rng.uniform(-8.8, -6.6)
            range_front = rng.uniform(0.45, 1.1)
            gyro_y += rng.uniform(0.15, 0.35)

        if label == "traffic_jam":
            range_front = rng.uniform(0.6, 1.8)
            range_left = rng.uniform(0.4, 1.4)

        if label == "fall_accident":
            accel_x = rng.choice([-1, 1]) * rng.uniform(21.0, 29.0)
            accel_y = rng.choice([-1, 1]) * rng.uniform(7.0, 13.0)
            accel_z = rng.uniform(12.0, 22.0)
            gyro_x = rng.choice([-1, 1]) * rng.uniform(2.3, 4.2)
            gyro_y = rng.choice([-1, 1]) * rng.uniform(1.8, 3.5)
            range_front = rng.uniform(0.2, 0.8)

        if spec.event_type == "fall_accident" and t > window["start"]:
            accel_x = rng.gauss(0.0, 0.08)
            accel_y = rng.gauss(0.0, 0.08)
            accel_z = rng.gauss(9.4, 0.25)
            gyro_x = rng.gauss(0.0, 0.02)
            gyro_y = rng.gauss(0.0, 0.02)
            gyro_z = rng.gauss(0.0, 0.02)
            range_front = rng.uniform(0.2, 1.0)

        battery = max(15.0, battery - rng.uniform(0.003, 0.010))
        rows.append(
            {
                "scenario_id": spec.scenario_id,
                "device_id": spec.device_id,
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "source": "simulated",
                "type": "telemetry",
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "speed": f"{speed_kmh:.2f}",
                "accel_x": f"{accel_x:.3f}",
                "accel_y": f"{accel_y:.3f}",
                "accel_z": f"{accel_z:.3f}",
                "gyro_x": f"{gyro_x:.4f}",
                "gyro_y": f"{gyro_y:.4f}",
                "gyro_z": f"{gyro_z:.4f}",
                "gps_accuracy_m": f"{rng.uniform(2.0, 6.5):.2f}",
                "range_front_m": f"{range_front:.2f}",
                "range_left_m": f"{range_left:.2f}",
                "ultrasonic_valid": "true",
                "battery": f"{battery:.1f}",
                "event_label": label,
            }
        )

        if label and (not events or events[-1]["event_type"] != label):
            trigger = {
                "hard_brake": "deceleration_threshold",
                "fall_accident": "accel_peak_exceeded",
                "traffic_jam": "prolonged_low_speed",
            }[label]
            events.append(
                {
                    "event_type": label,
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                    "expected_trigger": trigger,
                    "lat": round(lat, 7),
                    "lon": round(lon, 7),
                }
            )

        prev_speed_mps = speed_mps

        if spec.event_type == "fall_accident" and t >= window["start"] + 30:
            break
        if covered_m >= length_m and t > 45:
            break

    return rows, events


def write_dataset(
    output_root: Path,
    spec: ScenarioSpec,
    route_points: list[tuple[float, float]],
    route_m: float,
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    scenario_dir = output_root / spec.scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)

    telemetry_path = scenario_dir / "telemetry.csv"
    with telemetry_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    truth = {
        "scenario_id": spec.scenario_id,
        "device_id": spec.device_id,
        "description": spec.description,
        "source": "synthetic_osm_replay",
        "city": "Braga, Portugal",
        "route_length_m": round(route_m, 2),
        "sample_period_s": 1,
        "sensors": {
            "gps": ["lat", "lon", "speed", "gps_accuracy_m"],
            "imu": ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"],
            "ultrasonic": ["range_front_m", "range_left_m", "ultrasonic_valid"],
        },
        "events": events,
        "route_preview": [
            {"lat": round(lat, 7), "lon": round(lon, 7)}
            for lat, lon in route_points[:: max(1, len(route_points) // 12)]
        ],
    }
    (scenario_dir / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    return {
        "scenario_id": spec.scenario_id,
        "device_id": spec.device_id,
        "rows": len(rows),
        "route_length_m": round(route_m, 2),
        "event_types": [event["event_type"] for event in events],
        "telemetry_csv": str(telemetry_path.relative_to(REPO_ROOT)),
        "truth_json": str((scenario_dir / "truth.json").relative_to(REPO_ROOT)),
    }


def scenario_specs() -> list[ScenarioSpec]:
    return [
        ScenarioSpec(
            "normal_001",
            None,
            900,
            1700,
            15.0,
            "scooter_braga_001",
            "Percurso normal em Braga, sem eventos criticos.",
        ),
        ScenarioSpec(
            "normal_stop_and_go_001",
            None,
            1100,
            2100,
            13.5,
            "scooter_braga_002",
            "Percurso normal com paragens curtas compativeis com semaforos/cruzamentos.",
        ),
        ScenarioSpec(
            "normal_rough_pavement_001",
            None,
            900,
            1900,
            12.0,
            "scooter_braga_003",
            "Percurso sem acidente mas com vibracao de piso irregular para testar falsos positivos.",
        ),
        ScenarioSpec(
            "hard_brake_001",
            "hard_brake",
            1200,
            2300,
            16.5,
            "scooter_braga_004",
            "Travagem brusca com queda rapida de velocidade e desaceleracao longitudinal.",
        ),
        ScenarioSpec(
            "fall_accident_001",
            "fall_accident",
            1000,
            2200,
            14.0,
            "scooter_braga_005",
            "Queda/acidente com pico de aceleracao e imobilizacao posterior.",
        ),
        ScenarioSpec(
            "traffic_jam_001",
            "traffic_jam",
            1300,
            2600,
            12.5,
            "scooter_braga_006",
            "Congestionamento com velocidade muito baixa durante janela prolongada.",
        ),
        ScenarioSpec(
            "mixed_brake_jam_001",
            "mixed",
            1500,
            3000,
            15.0,
            "scooter_braga_007",
            "Percurso com travagem brusca e posterior congestionamento.",
        ),
        ScenarioSpec(
            "normal_short_center_001",
            None,
            550,
            1100,
            11.5,
            "scooter_braga_008",
            "Percurso curto urbano no centro de Braga, sem eventos criticos.",
        ),
        ScenarioSpec(
            "normal_commute_002",
            None,
            1600,
            2800,
            14.5,
            "scooter_braga_009",
            "Percurso normal de deslocacao casa-trabalho com distancia media.",
        ),
        ScenarioSpec(
            "normal_long_cross_city_001",
            None,
            2800,
            4200,
            16.0,
            "scooter_braga_010",
            "Percurso normal longo atravessando diferentes zonas da cidade.",
        ),
        ScenarioSpec(
            "normal_evening_return_001",
            None,
            1300,
            2400,
            13.0,
            "scooter_braga_011",
            "Percurso normal de regresso com velocidade moderada.",
        ),
        ScenarioSpec(
            "normal_peripheral_001",
            None,
            2200,
            3600,
            17.0,
            "scooter_braga_012",
            "Percurso normal em zonas mais perifericas de Braga.",
        ),
        ScenarioSpec(
            "hard_brake_roundabout_002",
            "hard_brake",
            800,
            1700,
            15.5,
            "scooter_braga_013",
            "Travagem brusca num percurso urbano curto.",
        ),
        ScenarioSpec(
            "hard_brake_crosswalk_003",
            "hard_brake",
            1600,
            2700,
            16.0,
            "scooter_braga_014",
            "Travagem brusca num percurso medio, simulando peao/passadeira.",
        ),
        ScenarioSpec(
            "fall_accident_curve_002",
            "fall_accident",
            650,
            1500,
            13.0,
            "scooter_braga_015",
            "Queda numa rota curta com imobilizacao posterior.",
        ),
        ScenarioSpec(
            "fall_accident_long_003",
            "fall_accident",
            1800,
            3200,
            15.0,
            "scooter_braga_016",
            "Queda/acidente depois de uma deslocacao mais longa.",
        ),
        ScenarioSpec(
            "traffic_jam_center_002",
            "traffic_jam",
            900,
            1800,
            11.5,
            "scooter_braga_017",
            "Congestionamento em percurso urbano central.",
        ),
        ScenarioSpec(
            "traffic_jam_long_003",
            "traffic_jam",
            2000,
            3400,
            13.5,
            "scooter_braga_018",
            "Congestionamento prolongado numa rota mais longa.",
        ),
        ScenarioSpec(
            "mixed_brake_jam_002",
            "mixed",
            1200,
            2400,
            14.0,
            "scooter_braga_019",
            "Travagem brusca seguida de fila de transito numa rota media.",
        ),
        ScenarioSpec(
            "mixed_brake_jam_003",
            "mixed",
            2400,
            3900,
            15.5,
            "scooter_braga_020",
            "Percurso longo com travagem brusca e congestionamento posterior.",
        ),
    ]


def generate(force_osm: bool = False) -> None:
    rng = random.Random(20260505)

    osm_data = fetch_osm_data(force=force_osm)
    nodes, graph = build_graph(osm_data)
    component = largest_component(graph)
    if len(component) < 100:
        raise RuntimeError("OpenStreetMap graph for Braga is unexpectedly small")

    if OUTPUT_ROOT.exists():
        for child in OUTPUT_ROOT.iterdir():
            if child.name not in {"_cache", "README.md"}:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    base_time = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)

    for index, spec in enumerate(scenario_specs()):
        route, route_m = choose_route(graph, component, rng, spec.min_route_m, spec.max_route_m)
        route_points = route_coordinates(nodes, route)
        rows, events = generate_rows(
            spec,
            route_points,
            rng,
            base_time + timedelta(minutes=index * 12),
        )
        manifest_entries.append(write_dataset(OUTPUT_ROOT, spec, route_points, route_m, rows, events))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": "scripts/generate_braga_datasets.py",
        "city": "Braga, Portugal",
        "coordinate_source": "OpenStreetMap via Overpass API",
        "bbox_south_west_north_east": BRAGA_BBOX,
        "sample_period_s": 1,
        "sensors_minimum": ["gps", "imu", "ultrasonic"],
        "datasets": manifest_entries,
    }
    (OUTPUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Generated {len(manifest_entries)} datasets in {OUTPUT_ROOT}")
    for entry in manifest_entries:
        events = ", ".join(entry["event_types"]) if entry["event_types"] else "none"
        print(f"- {entry['scenario_id']}: {entry['rows']} rows, {entry['route_length_m']}m, events={events}")


def main() -> None:
    force_osm = "--force-osm" in sys.argv
    generate(force_osm=force_osm)


if __name__ == "__main__":
    main()
