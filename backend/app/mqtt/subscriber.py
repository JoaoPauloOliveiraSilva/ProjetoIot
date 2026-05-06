import json
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from app.core.config import settings
from app.database import influx_db
from app.models.sensor import SensorData
from app.models.alert import AlertData
import ssl
from app.services.websocket_manager import manager
import asyncio
import traceback

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

fastapi_loop = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MqttQosStatus:
    connected: bool
    pending_total: int
    pending_qos1: int
    pending_qos0: int
    enqueued_total: int
    enqueued_qos1: int
    enqueued_qos0: int
    processed_total: int
    processed_qos1: int
    processed_qos0: int
    wait_ms_avg_60s_qos1: float
    wait_ms_p95_60s_qos1: float
    wait_ms_avg_60s_qos0: float
    wait_ms_p95_60s_qos0: float
    processing_ms_avg_60s_qos1: float
    processing_ms_p95_60s_qos1: float
    processing_ms_avg_60s_qos0: float
    processing_ms_p95_60s_qos0: float
    last_wait_ms: Optional[float]
    last_processing_ms: Optional[float]
    last_enqueued_at: Optional[str]
    last_processed_at: Optional[str]
    last_connected_at: Optional[str]
    last_disconnected_at: Optional[str]
    last_error: Optional[str]


class MqttIngestionQueue:
    def __init__(self) -> None:
        self._queue: queue.PriorityQueue[tuple[int, int, dict[str, Any]]] = queue.PriorityQueue()
        self._seq = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._window_sec = 60.0

        self._connected = False
        self._enqueued_total = 0
        self._enqueued_qos1 = 0
        self._enqueued_qos0 = 0
        self._processed_total = 0
        self._processed_qos1 = 0
        self._processed_qos0 = 0
        self._pending_qos1 = 0
        self._pending_qos0 = 0
        self._last_enqueued_at: Optional[str] = None
        self._last_processed_at: Optional[str] = None
        self._last_connected_at: Optional[str] = None
        self._last_disconnected_at: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_wait_ms: Optional[float] = None
        self._last_processing_ms: Optional[float] = None

        self._wait_samples_qos1: deque[tuple[float, float]] = deque()
        self._wait_samples_qos0: deque[tuple[float, float]] = deque()
        self._processing_samples_qos1: deque[tuple[float, float]] = deque()
        self._processing_samples_qos0: deque[tuple[float, float]] = deque()

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="mqtt-ingestion-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3)

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected
            if connected:
                self._last_connected_at = _now_iso()
            else:
                self._last_disconnected_at = _now_iso()

    def record_error(self, error: str) -> None:
        with self._lock:
            self._last_error = error

    def _trim_samples(self, now_ts: float) -> None:
        cutoff = now_ts - self._window_sec
        for d in (
            self._wait_samples_qos1,
            self._wait_samples_qos0,
            self._processing_samples_qos1,
            self._processing_samples_qos0,
        ):
            while d and d[0][0] < cutoff:
                d.popleft()

    def _stats(self, samples: deque[tuple[float, float]]) -> tuple[float, float]:
        if not samples:
            return 0.0, 0.0
        values = sorted(v for _t, v in samples)
        avg = sum(values) / len(values)
        idx = int(round(0.95 * (len(values) - 1)))
        p95 = values[max(0, min(len(values) - 1, idx))]
        return float(avg), float(p95)

    def enqueue(self, *, topic: str, payload: dict[str, Any], qos: int) -> None:
        priority = 0 if qos >= 1 else 1
        enqueued_ts = time.time()
        with self._lock:
            self._seq += 1
            seq = self._seq
            if qos >= 1:
                self._pending_qos1 += 1
                self._enqueued_qos1 += 1
            else:
                self._pending_qos0 += 1
                self._enqueued_qos0 += 1
            self._enqueued_total += 1
            self._last_enqueued_at = _now_iso()

        self._queue.put((priority, seq, {"topic": topic, "payload": payload, "qos": qos, "enqueued_ts": enqueued_ts}))

    def get_status(self) -> MqttQosStatus:
        with self._lock:
            now_ts = time.time()
            self._trim_samples(now_ts)
            wait_avg_qos1, wait_p95_qos1 = self._stats(self._wait_samples_qos1)
            wait_avg_qos0, wait_p95_qos0 = self._stats(self._wait_samples_qos0)
            proc_avg_qos1, proc_p95_qos1 = self._stats(self._processing_samples_qos1)
            proc_avg_qos0, proc_p95_qos0 = self._stats(self._processing_samples_qos0)
            return MqttQosStatus(
                connected=self._connected,
                pending_total=self._pending_qos0 + self._pending_qos1,
                pending_qos1=self._pending_qos1,
                pending_qos0=self._pending_qos0,
                enqueued_total=self._enqueued_total,
                enqueued_qos1=self._enqueued_qos1,
                enqueued_qos0=self._enqueued_qos0,
                processed_total=self._processed_total,
                processed_qos1=self._processed_qos1,
                processed_qos0=self._processed_qos0,
                wait_ms_avg_60s_qos1=wait_avg_qos1,
                wait_ms_p95_60s_qos1=wait_p95_qos1,
                wait_ms_avg_60s_qos0=wait_avg_qos0,
                wait_ms_p95_60s_qos0=wait_p95_qos0,
                processing_ms_avg_60s_qos1=proc_avg_qos1,
                processing_ms_p95_60s_qos1=proc_p95_qos1,
                processing_ms_avg_60s_qos0=proc_avg_qos0,
                processing_ms_p95_60s_qos0=proc_p95_qos0,
                last_wait_ms=self._last_wait_ms,
                last_processing_ms=self._last_processing_ms,
                last_enqueued_at=self._last_enqueued_at,
                last_processed_at=self._last_processed_at,
                last_connected_at=self._last_connected_at,
                last_disconnected_at=self._last_disconnected_at,
                last_error=self._last_error,
            )

    def _decrement_pending(self, qos: int) -> None:
        with self._lock:
            if qos >= 1:
                if self._pending_qos1 > 0:
                    self._pending_qos1 -= 1
            else:
                if self._pending_qos0 > 0:
                    self._pending_qos0 -= 1

    def _mark_processed(self, qos: int) -> None:
        with self._lock:
            self._processed_total += 1
            if qos >= 1:
                self._processed_qos1 += 1
            else:
                self._processed_qos0 += 1
            self._last_processed_at = _now_iso()

    def _process_message(self, *, topic: str, payload: dict[str, Any], qos: int) -> None:
        if topic.endswith("/telemetry"):
            from app.services.detection import analyze_telemetry

            sensor_data = SensorData(**payload)
            influx_db.save_sensor_data(sensor_data)
            generated_alert = analyze_telemetry(sensor_data)
            if generated_alert:
                influx_db.save_alert_data(generated_alert)
                if fastapi_loop and fastapi_loop.is_running():
                    alert_json = generated_alert.model_dump(mode="json")
                    asyncio.run_coroutine_threadsafe(manager.broadcast_alert(alert_json), fastapi_loop)
            return

        if topic.endswith("/alert") or topic.endswith("/alerts"):
            alert_data = AlertData(**payload)
            influx_db.save_alert_data(alert_data)
            if fastapi_loop and fastapi_loop.is_running():
                alert_json = alert_data.model_dump(mode="json")
                asyncio.run_coroutine_threadsafe(manager.broadcast_alert(alert_json), fastapi_loop)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                priority, seq, item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                qos = int(item.get("qos") or 0)
                topic = str(item.get("topic") or "")
                payload = item.get("payload") or {}
                enqueued_ts = float(item.get("enqueued_ts") or time.time())
                wait_ms = max(0.0, (time.time() - enqueued_ts) * 1000.0)
                self._decrement_pending(qos)
                start_processing = time.time()
                self._process_message(topic=topic, payload=payload, qos=qos)
                processing_ms = max(0.0, (time.time() - start_processing) * 1000.0)
                now_ts = time.time()
                with self._lock:
                    self._last_wait_ms = wait_ms
                    self._last_processing_ms = processing_ms
                    self._trim_samples(now_ts)
                    if qos >= 1:
                        self._wait_samples_qos1.append((now_ts, wait_ms))
                        self._processing_samples_qos1.append((now_ts, processing_ms))
                    else:
                        self._wait_samples_qos0.append((now_ts, wait_ms))
                        self._processing_samples_qos0.append((now_ts, processing_ms))
                self._mark_processed(qos)
            except Exception as exc:
                self.record_error(str(exc))
                logger.error(f"Erro ao processar mensagem MQTT na fila: {exc}")
                traceback.print_exc()
            finally:
                self._queue.task_done()


ingestion_queue = MqttIngestionQueue()

def _reason_code_value(reason_code):
    return int(getattr(reason_code, "value", reason_code))

def on_connect(client, userdata, flags, reason_code, properties=None):
    rc = _reason_code_value(reason_code)
    if rc == 0:
        logger.info(f"Ligado ao broker MQTT em {settings.MQTT_BROKER}:{settings.MQTT_PORT} (TLS: {settings.MQTT_TLS_ENABLED})")
        client.subscribe("/bike/+/telemetry",qos = 0)
        client.subscribe("/bike/+/alert",qos=1)
        client.subscribe("/bike/+/alerts",qos=1)
        logger.info("A escutar")
        ingestion_queue.set_connected(True)
    else:
        logger.info(f"Falha ao conectar ao mqtt: {rc}")    



def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    rc = _reason_code_value(reason_code)
    if rc!=0:
        logger.info("Desligado do mqtt")
    ingestion_queue.set_connected(False)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    
    try:
        data_dict = json.loads(payload)
        ingestion_queue.enqueue(topic=topic, payload=data_dict, qos=int(getattr(msg, "qos", 0) or 0))

    except json.JSONDecodeError:
        logger.error("Erro de Parsing: O JSON recebido não é válido.")
    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        # Isto vai imprimir as linhas a vermelho no terminal dizendo exatamente ONDE falhou
        traceback.print_exc()   

mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION2)

if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
    mqtt_client.username_pw_set(settings.MQTT_USERNAME,settings.MQTT_PASSWORD)

if settings.MQTT_TLS_ENABLED:
    if getattr(settings, "MQTT_TLS_CA_CERT", ""):
        mqtt_client.tls_set(
            ca_certs=settings.MQTT_TLS_CA_CERT,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        mqtt_client.tls_insecure_set(False)
    else:
        mqtt_client.tls_set(
            cert_reqs=ssl.CERT_NONE if getattr(settings, "MQTT_TLS_INSECURE", False) else ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        mqtt_client.tls_insecure_set(bool(getattr(settings, "MQTT_TLS_INSECURE", False)))

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect= on_disconnect
mqtt_client.on_message = on_message


def start_mqtt(loop):
    global fastapi_loop
    fastapi_loop = loop
    ingestion_queue.start()
    try:
        mqtt_client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"Erro ao iniciar o mqtt {e}")
        ingestion_queue.record_error(str(e))


def stop_mqtt():
    mqtt_client.loop_stop()  # <- ALTERAR AQUI (substituir o ponto por um underscore)
    mqtt_client.disconnect()
    ingestion_queue.stop()


def get_qos_status() -> dict[str, Any]:
    return asdict(ingestion_queue.get_status())
