from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorData(BaseModel):
    device_id: str
    source: str        
    type: str   
    timestamp: Optional[datetime] = None
    vehicle_type: Optional[str] = None
    trip_id: Optional[str] = None
    sequence: Optional[int] = None
    start_station_id: Optional[str] = None
    start_station_name: Optional[str] = None
    end_station_id: Optional[str] = None
    end_station_name: Optional[str] = None
    dock_status: Optional[str] = None
    charging: Optional[bool] = None
    lat: float        
    lon: float
    speed: float
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None
    gps_accuracy_m: Optional[float] = None
    range_front_m: Optional[float] = None
    range_left_m: Optional[float] = None
    ultrasonic_valid: Optional[bool] = None
    battery: Optional[float] = None
