from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import validar_api_key
from app.database import influx_db
from app.database.influx_db import InfluxDBError
from app.mqtt.subscriber import get_qos_status

router = APIRouter()


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"InfluxDB indisponível: {exc}")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _latest_session_id(rows: list[dict]) -> str | None:
    latest = None
    latest_session = None
    for row in rows:
        session_id = row.get("session_id")
        timestamp = _parse_timestamp(row.get("timestamp"))
        if not session_id or timestamp is None:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
            latest_session = session_id
    return latest_session


def _latest_devices(rows: list[dict], offline_after_sec: int) -> tuple[list[dict], int, int]:
    latest_by_device = {}
    for row in rows:
        device_id = row.get("device_id")
        timestamp = _parse_timestamp(row.get("timestamp"))
        if not device_id or timestamp is None:
            continue
        current = latest_by_device.get(device_id)
        if current is None or timestamp > current["timestamp_dt"]:
            latest_by_device[device_id] = {"timestamp_dt": timestamp, "latest": row}

    now = datetime.now(timezone.utc)
    devices = []
    for device_id, item in sorted(latest_by_device.items()):
        latest = item["latest"]
        age_sec = max(0.0, (now - item["timestamp_dt"]).total_seconds())
        online = age_sec <= offline_after_sec
        speed = float(latest.get("speed") or 0.0)
        dock_status = latest.get("dock_status")
        charging = latest.get("charging")
        if not online:
            operational = "offline"
        elif charging or dock_status == "charging":
            operational = "charging"
        elif dock_status:
            operational = "docked"
        elif speed > 1.0:
            operational = "moving"
        else:
            operational = "stopped"
        devices.append(
            {
                "device_id": device_id,
                "online": online,
                "status": "online" if online else "offline",
                "operational_state": operational,
                "last_seen": item["timestamp_dt"].isoformat(),
                "age_sec": round(age_sec, 1),
                "latest": latest,
            }
        )
    online_count = sum(1 for device in devices if device["online"])
    return devices, online_count, len(devices) - online_count


@router.get("/sessions/summary")
async def session_summary(
    session_id: Optional[str] = Query(None, description="Sessão de simulação a resumir; se omitida usa a mais recente"),
    minutos: int = Query(60, ge=1, description="Janela temporal para procurar sessões recentes"),
    offline_after_sec: int = Query(45, ge=1, description="Tempo sem telemetria para considerar dispositivo offline"),
    api_key: str = Depends(validar_api_key),
):
    try:
        if session_id:
            sensores = influx_db.get_recent_sensor_data(minutos=minutos, session_id=session_id)
            alertas = influx_db.get_recent_alerts(minutos=minutos, session_id=session_id)
        else:
            sensores = influx_db.get_recent_sensor_data(minutos=minutos)
            alertas = influx_db.get_recent_alerts(minutos=minutos)
            session_id = _latest_session_id(sensores + alertas)
            if session_id:
                sensores = [row for row in sensores if row.get("session_id") == session_id]
                alertas = [row for row in alertas if row.get("session_id") == session_id]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc

    if not session_id:
        return {
            "status": "waiting",
            "session_id": None,
            "message": "Nenhuma sessão de simulação recente encontrada.",
            "qos": get_qos_status(),
        }

    devices, online, offline = _latest_devices(sensores, offline_after_sec)
    timestamps = [
        ts
        for ts in (_parse_timestamp(row.get("timestamp")) for row in sensores + alertas)
        if ts is not None
    ]
    event_counts = Counter(row.get("event_type") or "unknown" for row in alertas)
    severity_counts = Counter(row.get("severity") or "info" for row in alertas)
    vehicle_counts = Counter((row.get("latest") or {}).get("vehicle_type") or "unknown" for row in devices)
    dumps = [row for row in alertas if row.get("event_type") == "dock_data_dump"]
    complete_dumps = [
        dump
        for dump in dumps
        if float(dump.get("completeness_pct") or 0.0) >= 99.9 and int(dump.get("missing_count") or 0) == 0
    ]

    return {
        "status": "sucesso",
        "session_id": session_id,
        "started_at": min(timestamps).isoformat() if timestamps else None,
        "last_seen": max(timestamps).isoformat() if timestamps else None,
        "telemetry_count": len(sensores),
        "alert_count": len(alertas),
        "event_counts": dict(event_counts),
        "severity_counts": dict(severity_counts),
        "vehicle_counts": dict(vehicle_counts),
        "devices_total": len(devices),
        "devices_online": online,
        "devices_offline": offline,
        "dock_dumps_total": len(dumps),
        "dock_dumps_complete": len(complete_dumps),
        "dock_dumps_incomplete": len(dumps) - len(complete_dumps),
        "dock_dumps_missing": sum(int(dump.get("missing_count") or 0) for dump in dumps),
        "offline_after_sec": offline_after_sec,
        "qos": get_qos_status(),
    }
