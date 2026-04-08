from fastapi import APIRouter
from app.models.alert import AlertData       
from app.database import influx_db           
from app.core.security import validar_api_key
from fastapi import APIRouter, Depends, Query, HTTPException

router = APIRouter()


@router.get("/devices")
async def Get_All_Devices(api_key: str = Depends(validar_api_key)
):
 
    dispositivos= influx_db.get_all_devices()
    
    return {
        "status": "sucesso",
        "total": len(dispositivos),
        "dispositivos": dispositivos     
    }


@router.get("/devices/{device_id}/latest")
async def Get_latest(device_id: str ,api_key: str = Depends(validar_api_key)
):
 
    estado= influx_db.get_latest_device_state(device_id)
    
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
 
    dados = influx_db.get_device_history(device_id, start, end)
    
    return {
        "status": "sucesso",
        "total_registos": len(dados),
        "dados": dados
    }      

