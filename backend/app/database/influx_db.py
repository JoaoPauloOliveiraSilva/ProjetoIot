from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from app.core.config import settings
from app.models.alert import AlertData 
from app.models.sensor import SensorData
import json
import logging
import re
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)
client = InfluxDBClient(url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()  

class InfluxDBError(RuntimeError):
    pass

_RELATIVE_TIME_RE = re.compile(r"^-\d+[smhdw]$")

def _flux_string(value: str) -> str:
    return json.dumps(value)

def _bucket() -> str:
    return _flux_string(settings.INFLUX_BUCKET)

def _minutes_range(minutos: int) -> str:
    if minutos < 1:
        raise ValueError("minutos deve ser maior ou igual a 1")
    return f"-{minutos}m"

def _time_expr(value: str, allow_relative: bool = True) -> str:
    value = value.strip()
    if value == "now()":
        return value
    if allow_relative and _RELATIVE_TIME_RE.fullmatch(value):
        return value
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Expressão temporal inválida: {value}") from exc
    return f"time(v: {_flux_string(value)})"

def _query_or_raise(query: str):
    try:
        return query_api.query(query=query, org=settings.INFLUX_ORG)
    except Exception as exc:
        logger.error(f"Erro ao consultar InfluxDB: {exc}")
        raise InfluxDBError(str(exc)) from exc

def ping() -> bool:
    try:
        return bool(client.ping())
    except Exception as exc:
        logger.error(f"Erro no ping ao InfluxDB: {exc}")
        return False


def get_latest_session_id(minutos: int = 60) -> Optional[str]:
    query = f"""
        from(bucket: {_bucket()})
          |> range(start: {_minutes_range(minutos)})
          |> filter(fn: (r) => r["_measurement"] == "Sensor" or r["_measurement"] == "Alert")
          |> filter(fn: (r) => r["_field"] == "lat")
          |> filter(fn: (r) => exists r.session_id)
          |> keep(columns: ["_time", "session_id"])
          |> group()
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
    """
    tabelas = _query_or_raise(query)
    for tabela in tabelas:
        for registo in tabela.records:
            return registo.values.get("session_id")
    return None

SENSOR_OPTIONAL_FIELDS = [
    "vehicle_type",
    "trip_id",
    "sequence",
    "start_station_id",
    "start_station_name",
    "end_station_id",
    "end_station_name",
    "dock_status",
    "charging",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "gps_accuracy_m",
    "range_front_m",
    "range_left_m",
    "ultrasonic_valid",
    "battery",
]

ALERT_OPTIONAL_FIELDS = [
    "vehicle_type",
    "trip_id",
    "station_id",
    "station_name",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "range_front_m",
    "range_left_m",
    "ultrasonic_valid",
    "charging",
    "battery_before",
    "battery_after",
    "expected_count",
    "sent_count",
    "received_count",
    "failed_count",
    "missing_count",
    "completeness_pct",
    "verification_status",
]

def _add_optional_fields(point: Point, data, fields: list[str]) -> Point:
    for field in fields:
        value = getattr(data, field, None)
        if value is not None:
            point = point.field(field, value)
    return point

def _alert_severity(data: AlertData) -> str:
    if data.severity:
        return data.severity
    if data.event_type == "fall_accident":
        return "critical"
    if data.event_type == "obstacle_risk":
        return "high"
    if data.event_type in {"hard_brake", "traffic_jam"}:
        return "warning"
    if data.event_type == "dock_data_dump" and (data.missing_count or 0) > 0:
        return "warning"
    return "info"

def _sensor_record(registo):
    return {
        "timestamp": registo.get_time().isoformat(),
        "device_id": registo.values.get("device_id"),
        "source": registo.values.get("source"),
        "type": registo.values.get("type"),
        "session_id": registo.values.get("session_id"),
        "vehicle_type": registo.values.get("vehicle_type"),
        "trip_id": registo.values.get("trip_id"),
        "sequence": registo.values.get("sequence"),
        "start_station_id": registo.values.get("start_station_id"),
        "start_station_name": registo.values.get("start_station_name"),
        "end_station_id": registo.values.get("end_station_id"),
        "end_station_name": registo.values.get("end_station_name"),
        "dock_status": registo.values.get("dock_status"),
        "charging": registo.values.get("charging"),
        "lat": registo.values.get("lat"),
        "lon": registo.values.get("lon"),
        "speed": registo.values.get("speed"),
        "accel_x": registo.values.get("accel_x"),
        "accel_y": registo.values.get("accel_y"),
        "accel_z": registo.values.get("accel_z"),
        "gyro_x": registo.values.get("gyro_x"),
        "gyro_y": registo.values.get("gyro_y"),
        "gyro_z": registo.values.get("gyro_z"),
        "gps_accuracy_m": registo.values.get("gps_accuracy_m"),
        "range_front_m": registo.values.get("range_front_m"),
        "range_left_m": registo.values.get("range_left_m"),
        "ultrasonic_valid": registo.values.get("ultrasonic_valid"),
        "battery": registo.values.get("battery"),
    }

def _alert_record(registo):
    return {
        "timestamp": registo.get_time().isoformat(),
        "device_id": registo.values.get("device_id"),
        "source": registo.values.get("source"),
        "type": registo.values.get("type"),
        "event_type": registo.values.get("event_type"),
        "trigger": registo.values.get("trigger"),
        "session_id": registo.values.get("session_id"),
        "severity": registo.values.get("severity"),
        "vehicle_type": registo.values.get("vehicle_type"),
        "trip_id": registo.values.get("trip_id"),
        "station_id": registo.values.get("station_id"),
        "station_name": registo.values.get("station_name"),
        "lat": registo.values.get("lat"),
        "lon": registo.values.get("lon"),
        "speed": registo.values.get("speed"),
        "accel_x": registo.values.get("accel_x"),
        "accel_y": registo.values.get("accel_y"),
        "accel_z": registo.values.get("accel_z"),
        "gyro_x": registo.values.get("gyro_x"),
        "gyro_y": registo.values.get("gyro_y"),
        "gyro_z": registo.values.get("gyro_z"),
        "range_front_m": registo.values.get("range_front_m"),
        "range_left_m": registo.values.get("range_left_m"),
        "ultrasonic_valid": registo.values.get("ultrasonic_valid"),
        "charging": registo.values.get("charging"),
        "battery_before": registo.values.get("battery_before"),
        "battery_after": registo.values.get("battery_after"),
        "expected_count": registo.values.get("expected_count"),
        "sent_count": registo.values.get("sent_count"),
        "received_count": registo.values.get("received_count"),
        "failed_count": registo.values.get("failed_count"),
        "missing_count": registo.values.get("missing_count"),
        "completeness_pct": registo.values.get("completeness_pct"),
        "verification_status": registo.values.get("verification_status"),
    }

def get_all_devices():
    query = f"""
        import "influxdata/influxdb/schema"
        schema.tagValues(bucket: {_bucket()}, tag: "device_id")
    """
    tabelas = _query_or_raise(query)
    dispositivos = [registo.get_value() for tabela in tabelas for registo in tabela.records]
    return dispositivos
    
def get_latest_device_state(device_id: str):
    """Obtém a última telemetria conhecida de um dispositivo."""
    query = f"""
        from(bucket: {_bucket()})
          |> range(start: -24h) // Procura na última janela de 24h
          |> filter(fn: (r) => r["_measurement"] == "Sensor")
          |> filter(fn: (r) => r["device_id"] == {_flux_string(device_id)})
          |> last()
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """
    tabelas = _query_or_raise(query)
    for tabela in tabelas:
        for registo in tabela.records:
            return _sensor_record(registo)
    return None

def get_device_history(device_id: str, start: str, end: str, session_id: Optional[str] = None):
    start_expr = _time_expr(start)
    end_expr = _time_expr(end)
    query = f"""
        from(bucket: {_bucket()})
          |> range(start: {start_expr}, stop: {end_expr})
          |> filter(fn: (r) => r["_measurement"] == "Sensor")
          |> filter(fn: (r) => r["device_id"] == {_flux_string(device_id)})
    """
    if session_id:
        query = query.rstrip() + f'\n          |> filter(fn: (r) => exists r.session_id and r.session_id == {_flux_string(session_id)})\n'
    query = query.rstrip() + '\n          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
    tabelas = _query_or_raise(query)
    resultados = []
    for tabela in tabelas:
        for registo in tabela.records:
            resultados.append(_sensor_record(registo))
    return resultados
    
    
        
def save_alert_data(data: AlertData):
    ponto = (
        Point("Alert")
        .tag("device_id", data.device_id)
        .tag("source", data.source)
        .tag("type", data.type)
        .tag("event_type", data.event_type)
        .tag("trigger", data.trigger)
        .field("severity", _alert_severity(data))
        .field("lat", data.lat)
        .field("lon", data.lon)
        .field("speed", data.speed if data.speed is not None else 0.0)
        .field("accel_x", data.accel_x if data.accel_x is not None else 0.0)
        .field("accel_y", data.accel_y if data.accel_y is not None else 0.0)
        .field("accel_z", data.accel_z if data.accel_z is not None else 0.0)
    )
    if data.session_id:
        ponto = ponto.tag("session_id", data.session_id)
    ponto = _add_optional_fields(ponto, data, ALERT_OPTIONAL_FIELDS)

    if data.timestamp:
        ponto = ponto.time(data.timestamp, WritePrecision.NS)

    try:
        write_api.write(
            bucket=settings.INFLUX_BUCKET,
            org=settings.INFLUX_ORG,
            record=ponto
        )
        logger.info(f"Alerta {data.device_id} gravado no InfluxDB")
    except Exception as e:
        logger.error(f"Erro ao gravar alerta no InfluxDB: {e}")
        raise InfluxDBError(str(e)) from e
        
        
def save_sensor_data(data: SensorData):
    ponto = (
        Point("Sensor")
        .tag("device_id", data.device_id)
        .tag("source", data.source)
        .tag("type", data.type)
        .field("lat", data.lat)
        .field("lon", data.lon)
        .field("speed", data.speed)
        .field("accel_x", data.accel_x)
        .field("accel_y", data.accel_y)
        .field("accel_z", data.accel_z)
    )
    if data.session_id:
        ponto = ponto.tag("session_id", data.session_id)
    ponto = _add_optional_fields(ponto, data, SENSOR_OPTIONAL_FIELDS)

    if data.timestamp:
        ponto = ponto.time(data.timestamp, WritePrecision.NS)

    try:
        write_api.write(
            bucket=settings.INFLUX_BUCKET,
            org=settings.INFLUX_ORG,
            record=ponto
        )
        logger.debug(f"Sensor {data.device_id} gravado no InfluxDB")
    except Exception as e:
        logger.error(f"Erro ao gravar sensor no InfluxDB: {e}")
        raise InfluxDBError(str(e)) from e
        
        

def get_recent_alerts(
    minutos: int,
    device_id: Optional[str] = None,
    event_type: Optional[str] = None,
    session_id: Optional[str] = None,
    severity: Optional[str] = None,
):
    query_lines = [
        f'from(bucket: {_bucket()})',
        f'  |> range(start: {_minutes_range(minutos)})',
        '  |> filter(fn: (r) => r["_measurement"] == "Alert")'
    ]
    
    if device_id:
        query_lines.append(f'  |> filter(fn: (r) => r["device_id"] == {_flux_string(device_id)})')
    if event_type:
        query_lines.append(f'  |> filter(fn: (r) => r["event_type"] == {_flux_string(event_type)})')
    if session_id:
        query_lines.append(f'  |> filter(fn: (r) => exists r.session_id and r.session_id == {_flux_string(session_id)})')

    query_lines.append('  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")')
    if severity:
        query_lines.append(f'  |> filter(fn: (r) => exists r.severity and r.severity == {_flux_string(severity)})')
    query = "\n".join(query_lines)
    
    tabelas = _query_or_raise(query)
    resultados = []
    for tabela in tabelas:
        for registo in tabela.records:
            resultados.append(_alert_record(registo))
    return resultados
    
def get_recent_sensor_data(
    minutos: int,
    device_id: Optional[str] = None,
    trip_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    query_lines = [
        f'from(bucket: {_bucket()})',
        f'  |> range(start: {_minutes_range(minutos)})',
        '  |> filter(fn: (r) => r["_measurement"] == "Sensor")'
    ]
    
    if device_id:
        query_lines.append(f'  |> filter(fn: (r) => r["device_id"] == {_flux_string(device_id)})')
    if session_id:
        query_lines.append(f'  |> filter(fn: (r) => exists r.session_id and r.session_id == {_flux_string(session_id)})')

    query_lines.append('  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")')
    if trip_id:
        query_lines.append(f'  |> filter(fn: (r) => exists r.trip_id and r.trip_id == {_flux_string(trip_id)})')
    query = "\n".join(query_lines)
    
    tabelas = _query_or_raise(query)
    resultados = []
    for tabela in tabelas:
        for registo in tabela.records:
            resultados.append(_sensor_record(registo))
    return resultados

def get_alerts_stats(minutos: int = 43200, device_id: Optional[str] = None, session_id: Optional[str] = None):
    query_lines = [
        f'from(bucket: {_bucket()})',
        f'  |> range(start: {_minutes_range(minutos)})',
        '  |> filter(fn: (r) => r["_measurement"] == "Alert")',
        '  |> filter(fn: (r) => r["_field"] == "lat")',
    ]
    if device_id:
        query_lines.append(f'  |> filter(fn: (r) => r["device_id"] == {_flux_string(device_id)})')
    if session_id:
        query_lines.append(f'  |> filter(fn: (r) => exists r.session_id and r.session_id == {_flux_string(session_id)})')
    query_lines.extend([
        '  |> group(columns: ["event_type"])',
        '  |> count()',
    ])
    query = "\n".join(query_lines)
    
    tabelas = _query_or_raise(query)
    estatisticas = {}
    for tabela in tabelas:
        for registo in tabela.records:
            evento = registo.values.get("event_type")
            estatisticas[evento] = registo.values.get("_value")
    return estatisticas

def close_db_client():
    write_api.close()
    query_api.close()
    client.close()
    logger.info("Ligação ao InfluxDB encerrada.")
