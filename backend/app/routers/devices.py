from app.database import influx_db           
from app.database.influx_db import InfluxDBError
from app.core.security import validar_api_key
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, timezone

router = APIRouter()

def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"InfluxDB indisponível: {exc}")

@router.get("/devices")
async def Get_All_Devices(api_key: str = Depends(validar_api_key)
):
 
    try:
        dispositivos= influx_db.get_all_devices()
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    return {
        "status": "sucesso",
        "total": len(dispositivos),
        "dispositivos": dispositivos     
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@router.get("/devices/status")
async def Get_Device_Status(
    minutos: int = Query(1440, ge=1, description="Janela de procura da última telemetria"),
    offline_after_sec: int = Query(60, ge=1, description="Tempo sem telemetria para considerar offline"),
    api_key: str = Depends(validar_api_key)
):
    try:
        sensores = influx_db.get_recent_sensor_data(minutos=minutos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc

    latest_by_device = {}
    for row in sensores:
        device_id = row.get("device_id")
        timestamp = _parse_timestamp(row.get("timestamp"))
        if not device_id or timestamp is None:
            continue
        current = latest_by_device.get(device_id)
        if current is None or timestamp > current["timestamp_dt"]:
            latest_by_device[device_id] = {"timestamp_dt": timestamp, "latest": row}

    now = datetime.now(timezone.utc)
    dispositivos = []
    for device_id, item in sorted(latest_by_device.items()):
        age_sec = max(0.0, (now - item["timestamp_dt"]).total_seconds())
        online = age_sec <= offline_after_sec
        dispositivos.append(
            {
                "device_id": device_id,
                "online": online,
                "status": "online" if online else "offline",
                "last_seen": item["timestamp_dt"].isoformat(),
                "age_sec": round(age_sec, 1),
                "latest": item["latest"],
            }
        )

    online_count = sum(1 for device in dispositivos if device["online"])
    return {
        "status": "sucesso",
        "total": len(dispositivos),
        "online": online_count,
        "offline": len(dispositivos) - online_count,
        "offline_after_sec": offline_after_sec,
        "dispositivos": dispositivos,
    }


@router.get("/devices/{device_id}/latest")
async def Get_latest(device_id: str ,api_key: str = Depends(validar_api_key)
):
 
    try:
        estado= influx_db.get_latest_device_state(device_id)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    return {
        "status": "sucesso",
        "dados": estado
    }  


@router.get("/devices/{device_id}/history")
async def Get_latest(device_id: str ,
    start: str = Query(..., description="Data de início (ex: -7d, ou timestamp ISO)"),
    end: str = Query("now()", description="Data de fim (ex: now(), ou timestamp ISO)"),
    api_key: str = Depends(validar_api_key)
):
 
    try:
        dados = influx_db.get_device_history(device_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    return {
        "status": "sucesso",
        "total_registos": len(dados),
        "dados": dados
    }      

