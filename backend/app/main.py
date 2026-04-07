from fastapi import FastAPI
from app.routers import telemetry, alerts
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from app.mqtt.subscriber import start_mqtt, stop_mqtt

load_dotenv(".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_mqtt()
    yield
    stop_mqtt()


app = FastAPI(title="IoT", lifespan=lifespan)
app.include_router(telemetry.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")

a