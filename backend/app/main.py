from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.routers import telemetry, alerts, devices, sessions
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from app.core.security import is_valid_api_key
from app.database import influx_db
from app.mqtt.subscriber import start_mqtt, stop_mqtt
from app.services.websocket_manager import manager  
import asyncio
from datetime import datetime, timezone

load_dotenv(".env")

SERVICE_STARTED_AT = datetime.now(timezone.utc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    start_mqtt(loop)
    yield
    stop_mqtt()

app = FastAPI(title="IoT", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "iot-backend",
        "started_at": SERVICE_STARTED_AT.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/health/ready")
async def readiness():
    if not influx_db.ping():
        raise HTTPException(status_code=503, detail="InfluxDB indisponível")
    return {
        "status": "ready",
        "service": "iot-backend",
        "started_at": SERVICE_STARTED_AT.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    api_key = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    if not is_valid_api_key(api_key):
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

app.include_router(telemetry.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
