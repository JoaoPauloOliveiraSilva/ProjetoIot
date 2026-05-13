from pydantic import BaseModel
from typing import Optional      
from datetime import datetime

class AlertData(BaseModel):
    device_id: str
    source: str        
    type: str   
    event_type: str
    timestamp: Optional[datetime] = None
    vehicle_type: Optional[str] = None
    trip_id: Optional[str] = None
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    lat: float        
    lon: float
    trigger: str
    speed: Optional[float] = None
    accel_x: Optional[float] = None
    accel_y: Optional[float] = None
    accel_z: Optional[float] = None
    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None
    range_front_m: Optional[float] = None
    range_left_m: Optional[float] = None
    ultrasonic_valid: Optional[bool] = None
    charging: Optional[bool] = None
    battery_before: Optional[float] = None
    battery_after: Optional[float] = None
    expected_count: Optional[int] = None
    sent_count: Optional[int] = None
    received_count: Optional[int] = None
    failed_count: Optional[int] = None
    missing_count: Optional[int] = None
    completeness_pct: Optional[float] = None
    verification_status: Optional[str] = None
