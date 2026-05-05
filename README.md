# Projeto IoT - Monitorização de Mobilidade Urbana Sustentável (P01)

Este projeto é uma plataforma completa de Internet of Things (IoT) desenvolvida para a monitorização colaborativa de mobilidade urbana (bicicletas, trotinetes), focada em segurança e eficiência.

## 🏗️ Arquitetura do Sistema
O sistema segue uma arquitetura modular em camadas:
- **Camada de Dispositivos (Edge)**: Representada pelo script de importação e simulação que processa dados de sensores (GPS, IMU).
- **Backend (FastAPI)**: Servidor Python que processa dados via HTTP/MQTT e executa algoritmos de deteção em tempo real.
- **Base de Dados (InfluxDB)**: Armazenamento Time Series rodando em Docker para telemetria e alertas.
- **Frontend (Dashboard)**: Interface interativa usando Leaflet (mapas), Chart.js (estatísticas) e WebSockets.

## 📊 Especificação de Dados (Data Specification)

Os datasets principais estão em `datasets/braga`, com rotas simuladas sobre ruas reais de Braga, Portugal. Cada cenário contém:

- `telemetry.csv`: telemetria temporal.
- `truth.json`: eventos esperados para validação.

Cada linha inclui pelo menos 3 sensores:

- GPS: `lat`, `lon`, `speed`, `gps_accuracy_m`
- IMU: `accel_x`, `accel_y`, `accel_z`, `gyro_x`, `gyro_y`, `gyro_z`
- Ultrassom: `range_front_m`, `range_left_m`, `ultrasonic_valid`

### 3. Requisitos de Ingestão via API
Se desejar enviar dados diretamente via REST API (`POST /api/v1/sensors`), o JSON deve respeitar o modelo `SensorData`:
```json
{
  "device_id": "string",
  "timestamp": "ISO8601 Datetime",
  "lat": 0.0,
  "lon": 0.0,
  "speed": 0.0,
  "accel_x": 0.0,
  "accel_y": 0.0,
  "accel_z": 0.0,
  "gyro_x": 0.0,
  "gyro_y": 0.0,
  "gyro_z": 0.0,
  "gps_accuracy_m": 3.0,
  "range_front_m": 4.2,
  "range_left_m": 1.5,
  "ultrasonic_valid": true,
  "battery": 100,
  "source": "manual/sensor",
  "type": "telemetry"
}
```

## 🛠️ Mapeamento de Requisitos e Fluxo de Código

### A. Algoritmos de Deteção Real-time
*   **Implementação**: [detection.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/services/detection.py)
*   **Fluxo**: Dado (API/MQTT) -> `analyze_telemetry()` -> Verificação de limites (Ex: Accel > 20 m/s²) -> Criação de `AlertData` -> Gravação no InfluxDB.

### B. Dashboard Interativo
*   **Implementação**: [index.html](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/index.html) e [alerts.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/routers/alerts.py)
*   **Fluxo**: `loadInitialData()` busca histórico via REST -> WebSocket manager empurra alertas em tempo real -> UI ordena decrescentemente (mais recente primeiro).
*   **API Key**: abrir o dashboard com `?api_key=...` guarda a chave no `localStorage` e evita credenciais hardcoded no HTML.

### C. Validação com Datasets de Braga
*   **Implementação**: [import_dataset.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/import_dataset.py)
*   **Fluxo**: Lê `datasets/braga/*/telemetry.csv` -> Envia via REST ou MQTT -> Ativa motor de deteção real-time.

### D. Segurança e QoS
*   **Segurança**: Middleware em [security.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/core/security.py) valida `X-API-Key`.
*   **MQTT**: Mosquitto local/Kubernetes usa username/password e `allow_anonymous false`.
*   **QoS**: Telemetria é publicada em `/bike/{id}/telemetry` com QoS 0; alertas críticos podem ser publicados em `/bike/{id}/alert` com QoS 1.

## 🚀 Como Executar

### 1. Executar Stack Completa com Docker Compose

```powershell
Copy-Item env.example .env
docker compose up --build
```

Serviços:

- Dashboard: `http://localhost:8080/?api_key=iot`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- Readiness: `http://localhost:8000/health/ready`
- InfluxDB: `http://localhost:18086` com `admin/adminadmin`
- MQTT: `localhost:1884` com `MQTT_USERNAME`/`MQTT_PASSWORD` do `.env`

### 2. Execução Manual do Backend

O InfluxDB e o Mosquitto devem estar a correr. Para iniciar apenas o backend:

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Reproduzir Datasets Simulados de Braga
O script `import_dataset.py` reproduz os cenários em `datasets/braga/*/telemetry.csv`.

```powershell
# Validar leitura dos cenários sem enviar dados
python import_dataset.py --mode dry-run

# Enviar por REST para o backend
python import_dataset.py --mode rest --api-key iot

# Enviar por MQTT com telemetria em QoS 0
python import_dataset.py --mode mqtt --mqtt-host localhost --mqtt-port 1884 --mqtt-username iot --mqtt-password iot

# Opcional: publicar também os alertas esperados do truth.json em /bike/{id}/alert com QoS 1
python import_dataset.py --mode mqtt --mqtt-username iot --mqtt-password iot --publish-truth-alerts
```

### 4. Validar Deteção nos Datasets
Compara os eventos esperados em `truth.json` com os alertas produzidos pelas regras do backend:

```powershell
python scripts\validate_braga_datasets.py --strict
```

### 5. Deploy Kubernetes

Os manifests em `k8s-manifests` criam namespace, Mosquitto autenticado, InfluxDB, backend e dashboard. Para a demo académica usam credenciais simples (`iot/iot` e `admin/adminadmin`).

```powershell
docker build -t iot-backend:latest .\backend
docker build -t iot-dashboard:latest -f .\frontend\Dockerfile .
ansible-playbook -i ansible\inventory.ini ansible\deploy-manifests.yml
```

No dashboard Kubernetes, configurar a API por query string:

```text
http://<node-ip>:30081/?api_base=http://<node-ip>:30080/api/v1&ws_url=ws://<node-ip>:30080/ws/alerts&api_key=iot
```

### 6. Simular Alerta Manual
