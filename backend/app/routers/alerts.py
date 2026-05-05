from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.alert import AlertData       
from app.database import influx_db           
from app.database.influx_db import InfluxDBError
from app.core.security import validar_api_key
from typing import Optional

router = APIRouter()

def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"InfluxDB indisponível: {exc}")

@router.post("/alerts")
async def receive_alert_data(data: AlertData,   
api_key: str = Depends(validar_api_key)
):
    
    try:
        influx_db.save_alert_data(data)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    return {
        "status": "sucesso", 
     
    }
    
@router.get("/alerts")
async def fetch_alerts(
    minutos: int = Query(60, ge=1, description="Minutos para trás"),
    device_id: Optional[str] = Query(None, description="Filtrar por dispositivo"),
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento (ex: hard_brake)"),
    api_key: str = Depends(validar_api_key)
):
    """Vai buscar alertas recentes, opcionalmente filtrados por tipo."""
    try:
        dados = influx_db.get_recent_alerts(minutos=minutos, device_id=device_id, event_type=event_type)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
        
    return {
        "status": "sucesso",
        "total_registos": len(dados),
        "dados": dados
    }
    
@router.get("/stats/alerts")
async def get_alert_statistics(
    minutos: int = Query(43200, ge=1, description="Minutos para trás"),
    device_id: Optional[str] = Query(None, description="Filtrar por dispositivo"),
    api_key: str = Depends(validar_api_key)
):
    """Estatísticas agregadas de alertas por tipo."""
    try:
        stats = influx_db.get_alerts_stats(minutos=minutos, device_id=device_id)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    return {
        "status": "sucesso",
        "estatisticas": stats
    }
