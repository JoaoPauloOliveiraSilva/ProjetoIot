import logging
from datetime import datetime, timezone
from app.models.sensor import SensorData
from app.models.alert import AlertData
from app.core.config import settings

logger = logging.getLogger(__name__)


device_states = {}

def create_alert(sensor: SensorData, event_type: str, trigger: str) -> AlertData:
    return AlertData(
        device_id=sensor.device_id,
        source=sensor.source,
        type="alert",
        event_type=event_type,
        timestamp=sensor.timestamp or datetime.now(timezone.utc),
        lat=sensor.lat,
        lon=sensor.lon,
        trigger=trigger,
        speed=sensor.speed,
        accel_x=sensor.accel_x,
        accel_y=sensor.accel_y,
        accel_z=sensor.accel_z,
        gyro_x=sensor.gyro_x,
        gyro_y=sensor.gyro_y,
        gyro_z=sensor.gyro_z,
        range_front_m=sensor.range_front_m,
        range_left_m=sensor.range_left_m,
        ultrasonic_valid=sensor.ultrasonic_valid
    )

def reset_detection_state():
    device_states.clear()

def _sample_time(data: SensorData) -> datetime:
    timestamp = data.timestamp or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)

def _seconds_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds())

def _can_emit(state: dict, event_type: str, current_time: datetime) -> bool:
    last_alerts = state.setdefault("last_alert_at", {})
    last_time = last_alerts.get(event_type)
    if last_time is None:
        last_alerts[event_type] = current_time
        return True
    if _seconds_between(last_time, current_time) >= settings.ALERT_COOLDOWN_SEC:
        last_alerts[event_type] = current_time
        return True
    return False

def analyze_telemetry(data: SensorData) -> AlertData | None:
    
    if data.device_id not in device_states:
        device_states[data.device_id] = {
            "jam_start_time": None,
            "jam_samples": 0,
            "jam_alerted": False,
            "last_alert_at": {}
        }
    state = device_states[data.device_id]
    current_time = _sample_time(data)
    
    max_accel = max([abs(data.accel_x), abs(data.accel_y), abs(data.accel_z)])
    
    if max_accel > settings.THRESHOLD_FALL_ACCEL and _can_emit(state, "fall_accident", current_time):
        logger.warning(f"Queda detetada no dispositivo {data.device_id}!")
        return create_alert(data, "fall_accident", "accel_peak_exceeded")
    
    if data.accel_y < settings.THRESHOLD_HARD_BRAKE and _can_emit(state, "hard_brake", current_time):
        logger.warning(f"Travagem brusca detetada no dispositivo {data.device_id}!")
        return create_alert(data, "hard_brake", "deceleration_threshold")

    if data.speed < settings.THRESHOLD_JAM_SPEED:
        if state["jam_start_time"] is None:
            state["jam_start_time"] = current_time
            state["jam_samples"] = 1
            state["jam_alerted"] = False
        else:
            state["jam_samples"] += 1
            duration = _seconds_between(state["jam_start_time"], current_time)
            enough_time = duration >= settings.JAM_TIME_WINDOW_SEC
            enough_samples = state["jam_samples"] >= settings.JAM_MIN_CONSECUTIVE_SAMPLES
            if (enough_time or enough_samples) and not state["jam_alerted"]:
                state["jam_alerted"] = True
                logger.warning(f"Congestionamento detetado no dispositivo {data.device_id}!")
                return create_alert(data, "traffic_jam", "prolonged_low_speed")
    else:
        state["jam_start_time"] = None
        state["jam_samples"] = 0
        state["jam_alerted"] = False

    return None
