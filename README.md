# Projeto IoT - Monitorização de Mobilidade Urbana Sustentável (P01)

Este projeto é uma plataforma completa de Internet of Things (IoT) desenvolvida para a monitorização colaborativa de mobilidade urbana (bicicletas, trotinetes), focada em segurança e eficiência.

## 🏗️ Arquitetura do Sistema
O sistema segue uma arquitetura modular em camadas:
- **Camada de Dispositivos (Edge)**: Representada pelo script de importação e simulação que processa dados de sensores (GPS, IMU).
- **Backend (FastAPI)**: Servidor Python que processa dados via HTTP/MQTT e executa algoritmos de deteção em tempo real.
- **Base de Dados (InfluxDB)**: Armazenamento Time Series rodando em Docker para telemetria e alertas.
- **Frontend (Dashboard)**: Interface interativa usando Leaflet (mapas), Chart.js (estatísticas) e WebSockets.

## 📊 Especificação de Dados (Data Specification)

Para que novos dados sejam importados corretamente via `import_dataset.py`, eles devem seguir as seguintes normas:

### 1. Estrutura de Pastas
O script espera uma hierarquia organizada por rotas e voltas:
`Dataset_Root / [Route Name] / [Lap Name] /`
- Exemplo: `Bike&Safe Dataset / First route / First lap /`

### 2. Formato dos Ficheiros (CSV)
Cada subpasta de "Lap" deve conter pelo menos dois ficheiros identificáveis por palavras-chave no nome:

- **Ficheiro GPS** (deve conter `GPS` no nome):
  - **Formato**: CSV (separador `,` ou `;`).
  - **Colunas obrigatórias**:
    1. `Tipo` (deve ser a string "GPS").
    2. `Latitude` (float).
    3. `Longitude` (float).
    4. `Velocidade` (float em m/s - o script converte para km/h).
    5. `Timestamp` (float em milissegundos Unix).

- **Ficheiro de Acelerómetro** (deve conter `accelerometer` no nome):
  - **Formato**: CSV (separador `,` ou `;`).
  - **Colunas obrigatórias**:
    1. `Timestamp` (nanossegundos ou ID sequencial).
    2. `Sensor ID` (ignorável).
    3. `Accel X` (float).
    4. `Accel Y` (float).
    5. `Accel Z` (float).

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

### C. Validação com Datasets (Bike&Safe)
*   **Implementação**: [import_dataset.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/import_dataset.py)
*   **Fluxo**: Lê CSVs brutos -> Sincroniza GPS/IMU -> Envia via API POST -> Ativa motor de deteção real-time.

### D. Segurança e QoS
*   **Segurança**: Middleware em [security.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/core/security.py) valida `X-API-Key`.
*   **QoS (Pendente)**: Implementação de Priority Queue para eventos críticos.

## 🚀 Como Executar

### 1. Iniciar Base de Dados (Docker)
O InfluxDB deve estar a correr no Docker local:
```powershell
docker ps | findstr influx
# Caso precise listar o token:
docker exec influxdb-iot influx auth list --json
```

### 2. Configurar e Iniciar Backend
```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Importar Dados do Dataset
O script de importação permite carregar os dados do Bike&Safe Dataset. Por padrão, ele procura na pasta de Downloads, mas você pode passar um caminho personalizado:

```powershell
# Usando o caminho padrão
python import_dataset.py

# Usando um caminho personalizado (útil para outros membros da equipe)
python import_dataset.py "C:\Caminho\Para\Seu\Dataset"
```

### 4. Simular Alerta Manual

```

---
