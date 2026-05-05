from app.database import influx_db           
from app.database.influx_db import InfluxDBError
from app.core.security import validar_api_key
from fastapi import APIRouter, Depends, Query, HTTPException

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

