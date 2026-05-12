import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("INFLUX_TOKEN", "test-token")
os.environ.setdefault("INFLUX_ORG", "test-org")
os.environ.setdefault("INFLUX_BUCKET", "Iot")
os.environ.setdefault("INFLUX_URL", "http://localhost:8086")
os.environ.setdefault("API_KEY_EDGE", "test-key")

from app.models.sensor import SensorData  # noqa: E402
from app.services.detection import analyze_telemetry, reset_detection_state  # noqa: E402


def sample(**overrides):
    payload = {
        "device_id": "scooter_test_001",
        "source": "unit_test",
        "type": "telemetry",
        "timestamp": datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        "lat": 41.55,
        "lon": -8.42,
        "speed": 12.0,
        "accel_x": 0.0,
        "accel_y": 0.0,
        "accel_z": 9.81,
        "gyro_x": 0.0,
        "gyro_y": 0.0,
        "gyro_z": 0.0,
        "range_front_m": 4.0,
        "range_left_m": 1.4,
        "ultrasonic_valid": True,
        "battery": 95.0,
    }
    payload.update(overrides)
    return SensorData(**payload)


class DetectionTests(unittest.TestCase):
    def setUp(self):
        reset_detection_state()

    def test_fall_accident(self):
        alert = analyze_telemetry(sample(accel_x=24.0))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "fall_accident")

    def test_hard_brake(self):
        alert = analyze_telemetry(sample(accel_y=-7.2))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "hard_brake")

    def test_obstacle_risk_from_ultrasonic(self):
        alert = analyze_telemetry(sample(range_front_m=0.35, speed=11.0))
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "obstacle_risk")
        self.assertEqual(alert.trigger, "front_range_threshold")

    def test_traffic_jam_uses_sample_timestamps(self):
        start = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
        alert = None
        for idx in range(61):
            alert = analyze_telemetry(
                sample(
                    timestamp=start + timedelta(seconds=idx),
                    speed=1.0,
                    accel_y=0.0,
                    range_front_m=2.0,
                )
            )
            if alert:
                break
        self.assertIsNotNone(alert)
        self.assertEqual(alert.event_type, "traffic_jam")

    def test_normal_sample_has_no_alert(self):
        alert = analyze_telemetry(sample(speed=15.0, accel_x=0.1, accel_y=0.0, accel_z=9.7))
        self.assertIsNone(alert)


if __name__ == "__main__":
    unittest.main()
