# Braga Micromobility Simulation Datasets

Synthetic datasets for simulating scooters and bicycles in Braga, Portugal. Routes were generated over street and cycleway geometry obtained from OpenStreetMap through the Overpass API.

## Structure

Each scenario contains:

- `telemetry.csv`: time-ordered telemetry samples.
- `truth.json`: expected events for validation.

The `manifest.json` file summarizes all 100 generated scenarios: 50 scooter scenarios and 50 bicycle scenarios.

## Included Sensors

Each telemetry row includes data from at least three sensor groups:

- GPS: `lat`, `lon`, `speed`, `gps_accuracy_m`
- IMU: `accel_x`, `accel_y`, `accel_z`, `gyro_x`, `gyro_y`, `gyro_z`
- Ultrasonic: `range_front_m`, `range_left_m`, `ultrasonic_valid`

Bicycle scenarios also include:

- `vehicle_type=bicycle`
- `start_station_id`, `start_station_name`
- `end_station_id`, `end_station_name`
- `dock_status` and `charging`

At the end of a bicycle trip, the bicycle remains stopped at the final station for a few samples with `charging=true`. The simulator uses this metadata to publish the operational `dock_data_dump` event, which summarizes whether the data dump was complete. This event compares the expected trip rows with the rows effectively received by the backend for that trip's `trip_id`. Every bicycle scenario starts at a station and ends at a station, which may be the same one.

## Scenarios

The dataset combines normal routes, hard braking, falls/accidents, traffic jams, ultrasonic obstacle risk, and mixed scenarios. The names below show the main families; numbered variants complete the 50 routes for each vehicle type.

### Scooters

- `normal_001`: normal route without a critical event.
- `normal_stop_and_go_001`: normal route with short stops.
- `normal_rough_pavement_001`: rough pavement without an accident, useful for testing false positives.
- `hard_brake_001`: hard braking.
- `fall_accident_001`: fall/accident with an acceleration peak.
- `traffic_jam_001`: prolonged traffic jam.
- `obstacle_risk_001`: nearby obstacle detected by ultrasound.
- `mixed_brake_jam_001`: hard braking followed by congestion.

### Bicycles

- `bike_normal_center_001`: normal city-center route with docking at the end.
- `bike_commute_center_002`: short trip between central stations.
- `bike_evening_return_003`: late-afternoon return trip.
- `bike_hard_brake_center_001`: hard braking.
- `bike_fall_accident_center_001`: fall/accident.
- `bike_traffic_jam_center_001`: traffic jam.
- `bike_obstacle_risk_center_001`: nearby obstacle.
- `bike_mixed_brake_jam_center_001`: hard braking followed by congestion.

## Regeneration

```powershell
python scripts\generate_braga_datasets.py
```

To force a new OSM data download:

```powershell
python scripts\generate_braga_datasets.py --force-osm
```

## Attribution

Street data derived from OpenStreetMap. Attribution: OpenStreetMap contributors.
