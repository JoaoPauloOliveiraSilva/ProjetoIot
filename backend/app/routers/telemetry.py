from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.sensor import SensorData       
from app.database import influx_db           
from app.database.influx_db import InfluxDBError
from app.core.security import validar_api_key
from app.services.detection import analyze_telemetry
from app.services.websocket_manager import manager
from app.mqtt.subscriber import get_qos_status

router = APIRouter()

def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"InfluxDB indisponível: {exc}")

@router.post("/sensors")
async def receive_alert_data(data: SensorData,
                             api_key: str = Depends(validar_api_key)
):
    
    try:
        influx_db.save_sensor_data(data)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    # Adicionar lógica de deteção para dados recebidos via API
    generated_alert = analyze_telemetry(data)
    if generated_alert:
        try:
            influx_db.save_alert_data(generated_alert)
        except InfluxDBError as exc:
            raise _db_unavailable(exc) from exc
        # Tentar enviar via WebSocket se possível
        try:
            alert_json = generated_alert.model_dump(mode="json")
            await manager.broadcast_alert(alert_json)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Falha no broadcast WebSocket: {exc}") from exc
    
    return {
        "status": "sucesso", 
     
    }
    
@router.get("/sensors")
def fetch_alerts(
    minutos: int = Query(60, ge=1, description="Minutos para trás"),
    device_id: str | None = Query(None, description="Filtrar por dispositivo"),
    trip_id: str | None = Query(None, description="Filtrar por viagem simulada"),
    session_id: str | None = Query(None, description="Filtrar por sessão de simulação"),
    api_key: str = Depends(validar_api_key)
):

    try:
        dados = influx_db.get_recent_sensor_data(minutos=minutos, device_id=device_id, trip_id=trip_id, session_id=session_id)
    except InfluxDBError as exc:
        raise _db_unavailable(exc) from exc
    
    return {
        "status": "sucesso",
        "total_registos": len(dados),
        "dados": dados
    }


@router.get("/qos/status")
def qos_status(api_key: str = Depends(validar_api_key)):
    return {"status": "sucesso", "qos": get_qos_status()}
