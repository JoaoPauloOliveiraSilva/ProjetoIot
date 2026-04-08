from fastapi import APIRouter
from app.models.alert import AlertData       
from app.database import influx_db           
from app.core.security import validar_api_key
from fastapi import APIRouter, Depends, Query
from typing import Optional

router = APIRouter()

@router.post("/alerts")
async def receive_alert_data(data: AlertData,   
api_key: str = Depends(validar_api_key)
):
    
    influx_db.save_alert_data(data)
    
    return {
        "status": "sucesso", 
     
    }
    
@router.get("/alerts")
async def fetch_alerts(
    minutos: int = Query(60, description="Minutos para trás"), 
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento (ex: hard_brake)"),
    api_key: str = Depends(validar_api_key)
):
    """Vai buscar alertas recentes, opcionalmente filtrados por tipo."""
    dados = influx_db.get_recent_alerts(minutos=minutos)
    
    if event_type:
        dados = [d for d in dados if d.get("event_type") == event_type]
        
    return {
        "status": "sucesso",
        "total_registos": len(dados),
        "dados": dados
    }
    
@router.get("/stats/alerts")
async def get_alert_statistics(api_key: str = Depends(validar_api_key)):
    """Estatísticas agregadas de alertas por tipo."""
    stats = influx_db.get_alerts_stats()
    return {
        "status": "sucesso",
        "estatisticas": stats
    }