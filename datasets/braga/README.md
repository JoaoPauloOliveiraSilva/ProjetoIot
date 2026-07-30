# Braga Micromobility Simulation Dataset

This folder contains the synthetic Braga dataset. The dataset models shared scooters and bicycles moving through Braga, Portugal, using georeferenced trajectories generated from OpenStreetMap road and cycleway geometry obtained through the Overpass API.

The dataset exists because collecting real falls, crash-like incidents, hard braking, prolonged congestion, and connectivity edge cases on public roads is unsafe and difficult to repeat. Here, those cases are controlled, labelled, and reproducible, so the platform can be tested end to end against known ground truth.

## Key Idea

Each scenario folder inside `datasets/braga/` represents one different route/path through Braga.

For example, `normal_001/`, `hard_brake_001/`, `bike_normal_center_001/`, and `bike_fall_accident_center_001/` are not just labels: each folder contains a separate trajectory with its own coordinates, timestamps, sensor readings, route length, and expected events. Folders with similar names belong to the same scenario family, but they still represent distinct generated routes.

## Dataset Summary

| Item | Value |
| --- | --- |
| City | Braga, Portugal |
| Coordinate source | OpenStreetMap via Overpass API |
| Total scenarios/routes | 100 |
| Scooter routes | 50 |
| Bicycle routes | 50 |
| Sampling period | 1 second |
| Samples per route | 178 to 909 rows |
| Route length | 637.67 m to 3977.49 m |
| Average route length | 1735.03 m |
| Main validation target | Event detection and trip-level data completeness |

## Folder Layout

```text
datasets/braga/
  README.md
  manifest.json
  bike_stations.json
  normal_001/
    telemetry.csv
    truth.json
  hard_brake_001/
    telemetry.csv
    truth.json
  bike_normal_center_001/
    telemetry.csv
    truth.json
  ...
```

Top-level files:

- `manifest.json`: global index of all 100 scenarios, including vehicle type, row count, route length, expected event types, station metadata, and file paths.
- `bike_stations.json`: modeled bicycle docking stations used by bicycle scenarios.
- `README.md`: this documentation.

Scenario folders:

- `telemetry.csv`: time-ordered samples replayed by the simulator or dataset importer.
- `truth.json`: machine-readable ground truth for the route, including scenario metadata, sensor groups, expected events, route preview points, and bicycle docking information when applicable.

## Telemetry Schema

Each `telemetry.csv` row represents one sample emitted by a simulated vehicle. The main fields are:

| Group | Fields |
| --- | --- |
| Scenario identity | `scenario_id`, `device_id`, `vehicle_type`, `trip_id`, `sequence` |
| Time and source | `timestamp`, `source`, `type` |
| GPS | `lat`, `lon`, `speed`, `gps_accuracy_m` |
| IMU | `accel_x`, `accel_y`, `accel_z`, `gyro_x`, `gyro_y`, `gyro_z` |
| Ultrasonic proximity | `range_front_m`, `range_left_m`, `ultrasonic_valid` |
| Vehicle state | `battery`, `dock_status`, `charging` |
| Bicycle station context | `start_station_id`, `start_station_name`, `end_station_id`, `end_station_name` |
| Validation helper | `event_label` |

All routes include GPS, IMU, ultrasonic proximity, battery, and operational-state fields. Bicycle routes also include docking station fields.

## Ground Truth

Each `truth.json` file describes what should happen in that route:

- `scenario_id`, `device_id`, `vehicle_type`, `city`, and `source`.
- `route_length_m` and `sample_period_s`.
- `sensors`, listing the sensor fields used for validation.
- `events`, listing expected critical events with type, timestamp, location, and expected trigger.
- `route_preview`, a compact list of representative coordinates for the route.
- `start_station`, `end_station`, and `data_dump` for bicycle scenarios.

Normal routes intentionally contain no target event. Critical routes include the expected annotation in `truth.json`, allowing backend detections to be compared with ground truth for true positives, false positives, false negatives, precision, and recall.

## Scenario Distribution

| Scenario family | Scooter | Bicycle | Total | Purpose |
| --- | ---: | ---: | ---: | --- |
| Normal | 17 | 18 | 35 | Validate ordinary trips and absence of false alerts |
| Hard braking | 9 | 11 | 20 | Validate sudden deceleration detection |
| Fall or accident | 9 | 6 | 15 | Validate acceleration-peak accident detection |
| Traffic jam | 7 | 5 | 12 | Validate prolonged low-speed/congestion detection |
| Mixed braking and jam | 5 | 5 | 10 | Validate routes with more than one event pattern |
| Obstacle risk | 3 | 5 | 8 | Validate ultrasonic proximity risk detection |
| Total | 50 | 50 | 100 | Complete dataset |

## Naming Notes

Scenario names encode the vehicle type, scenario family, rough route context, and numeric variant when applicable.

- Bicycle folders use the `bike_` prefix, for example `bike_normal_center_001`.
- Scooter folders include both older unprefixed names such as `normal_001` and explicit names such as `scooter_normal_center_022`.
- The canonical vehicle type is always the `vehicle_type` field in `manifest.json`, `telemetry.csv`, and `truth.json`.
- Numbered variants are different routes, not duplicate copies.

## Bicycle Docking and Data Completeness

Bicycle scenarios start and end at modeled docking stations in central Braga. At the end of a bicycle trip, the bicycle remains stopped at the final station for a few samples with `charging=true`.

This final docking state is used by the platform to publish a `dock_data_dump` reconciliation event. That event compares the expected trip rows with the rows transmitted and persisted by the backend for the same `trip_id`. The purpose is to make silent telemetry loss measurable instead of leaving the dashboard to assume that a trip was complete.

## How This Dataset Is Used

The dataset can be replayed through the project importer or simulator:

```powershell
python import_dataset.py --mode dry-run
```

Replay a single scenario through REST:

```powershell
python import_dataset.py --mode rest --api-key iot --scenario fall_accident_001
```

Replay all scenarios through MQTT/TLS:

```powershell
python import_dataset.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.crt --mqtt-host localhost --mqtt-port 8883 --mqtt-username iot --mqtt-password iot
```

Validate the dataset files:

```powershell
python scripts\validate_braga_datasets.py --strict
```

## Regeneration

Regenerate the Braga dataset:

```powershell
python scripts\generate_braga_datasets.py
```

Force a new OpenStreetMap download before regeneration:

```powershell
python scripts\generate_braga_datasets.py --force-osm
```

## Validity Boundaries

This is a synthetic dataset. It is suitable for reproducible validation of the platform architecture, data model, event rules, QoS behavior, replay flow, and dashboard/backend processing. It should not be interpreted as a calibrated real-world sensor benchmark.

The data may not capture all real effects of GPS multipath, sensor drift, mounting differences, rider behavior, weather, road surface variation, or correlated wireless-network failures. Real deployments should recalibrate thresholds and validate performance with field data.

## Attribution

Street and cycleway geometry derived from OpenStreetMap. Attribution: OpenStreetMap contributors.
