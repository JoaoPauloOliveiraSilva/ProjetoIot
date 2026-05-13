# Projeto IoT - Monitorização de Mobilidade Urbana Sustentável (P01)

Este projeto é uma plataforma completa de Internet of Things (IoT) desenvolvida para a monitorização colaborativa de mobilidade urbana (bicicletas, trotinetes), focada em segurança e eficiência.

## 🏗️ Arquitetura do Sistema
O sistema segue uma arquitetura modular em camadas:
- **Camada de Dispositivos (Edge)**: Representada pelo script de importação e simulação que processa dados de sensores (GPS, IMU e ultrassom).
- **Backend (FastAPI)**: Servidor Python que processa dados via HTTP/MQTT e executa algoritmos de deteção em tempo real.
- **Base de Dados (InfluxDB)**: Armazenamento Time Series rodando em Docker para telemetria e alertas.
- **Frontend (Dashboard)**: Interface interativa usando Leaflet (mapas), Chart.js (estatísticas) e WebSockets.

## 📊 Especificação de Dados (Data Specification)

Os datasets principais estão em `datasets/braga`, com 100 rotas simuladas sobre ruas reais de Braga, Portugal: 50 cenários de trotinetes e 50 cenários de bicicletas, com prioridade para rotas centrais nas bicicletas. Cada cenário contém:

- `telemetry.csv`: telemetria temporal.
- `truth.json`: eventos esperados para validação.

Os cenários de bicicleta incluem ainda `vehicle_type=bicycle`, estação inicial/final, estado de docking e amostras finais de carregamento. Todas as bicicletas começam e terminam numa estação. Quando usados no simulador contínuo por MQTT, o fim da viagem publica um alerta QoS 1 `dock_data_dump`, com contadores de linhas esperadas, enviadas, falhadas, em falta e percentagem de completude da descarga de dados.

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
*   **Fluxo**: Dado (API/MQTT) -> `analyze_telemetry()` -> Verificação de limites (aceleração, travagem, velocidade prolongadamente baixa e distância frontal por ultrassom) -> Criação de `AlertData` -> Gravação no InfluxDB.
*   **Eventos**: `fall_accident`, `hard_brake`, `traffic_jam` e `obstacle_risk`.
*   **Eventos operacionais**: bicicletas também podem gerar `dock_data_dump` no fim da viagem, quando são deixadas numa estação para carregamento e descarga de dados.

### B. Dashboard Interativo
*   **Implementação**: [index2.html](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/index2.html) e [alerts.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/routers/alerts.py)
*   **Fluxo**: a dashboard consulta REST para telemetria/dispositivos/QoS, recebe alertas por WebSocket e mostra também as estações de bicicletas e as descargas `dock_data_dump`.
*   **API Key**: abrir o dashboard com `?api_key=...` guarda a chave no `localStorage` e evita credenciais hardcoded no HTML.

### C. Validação com Datasets de Braga
*   **Implementação**: [import_dataset.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/import_dataset.py)
*   **Fluxo**: Lê `datasets/braga/*/telemetry.csv` -> Envia via REST ou MQTT -> Ativa motor de deteção real-time.

### D. Segurança e QoS
*   **Segurança**: Middleware em [security.py](file:///c:/Users/38240/Documents/GitHub/ProjetoIot/backend/app/core/security.py) valida `X-API-Key`.
*   **MQTT**: Mosquitto local/Kubernetes usa username/password e `allow_anonymous false`.
*   **QoS**: Telemetria é publicada em `/bike/{id}/telemetry` com QoS 0; alertas críticos podem ser publicados em `/bike/{id}/alert` com QoS 1.
*   **Visualização de QoS (fila)**: o backend mantém uma fila interna de ingestão MQTT e expõe métricas em `GET /api/v1/qos/status` (mostra pendentes/processados por QoS 0/1). O dashboard mostra estas métricas no cartão “Fila MQTT (QoS)”.
*   **Estado dos dispositivos**: `GET /api/v1/devices/status` calcula online/offline pela última telemetria recebida.

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
- MQTT (TLS): `localhost:8883` com `MQTT_USERNAME`/`MQTT_PASSWORD` do `.env`

O comando `docker compose up --build` inicia a stack completa: Mosquitto, InfluxDB, backend, dashboard e simulador Docker.

```powershell
docker compose up --build
```

O serviço `iot-simulator` lê os datasets em `datasets/braga`, publica telemetria em MQTT TLS para o broker, e o backend processa/persiste os dados e propaga alertas por WebSocket.

#### Verificar TLS + CA (MQTT)

O broker MQTT expõe apenas TLS em `8883`. Isso fornece encriptação em trânsito e permite validar a identidade do broker via CA (evita ataques do tipo man-in-the-middle).

1) Confirmar que a porta sem TLS (1883) não está disponível:

```powershell
Test-NetConnection localhost -Port 1883
```

Resultado esperado:
- `TcpTestSucceeded : False` (ou `WARNING: TCP connect ... failed`)

Porquê:
- Confirma que não existe listener em `1883` (porta típica de MQTT sem TLS). Isto reduz o risco de alguém publicar/consumir dados em claro por engano.

2) Exportar o certificado da CA gerado no container (para validação do servidor):

```powershell
docker cp iot-mosquitto:/mosquitto/data/tls/ca.crt .\mosquitto-ca.crt
```

Resultado esperado:
- Sem mensagens de erro (o comando normalmente não imprime nada).
- O ficheiro `.\mosquitto-ca.crt` passa a existir.

Porquê:
- O `ca.crt` é a “âncora de confiança” usada pelo cliente para validar o certificado TLS apresentado pelo broker. Sem isto, ou não há validação, ou é necessário usar modo inseguro.

3) Teste “TLS com validação” (deve funcionar):

```powershell
python .\import_dataset.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.crt --mqtt-host localhost --mqtt-port 8883 --mqtt-username iot --mqtt-password iot --scenario fall_accident_001 --publish-truth-alerts
```

Resultado esperado:
- O script imprime linhas do tipo:
  - `fall_accident_001: sent=... failed=0 rows=...`
  - `Done: sent=... failed=0 mode=mqtt`

Porquê:
- O MQTT está a ser usado sobre TLS (`--mqtt-tls`) e o certificado do broker foi validado contra a CA (`--mqtt-ca-cert`). Se a validação falhasse, a ligação não seria estabelecida e o envio não avançaria.
- `--publish-truth-alerts` força a publicação de eventos “críticos” do `truth.json` em `/bike/{id}/alert` com QoS 1, permitindo observar diferenciação entre QoS 0 (telemetria) e QoS 1 (alertas).

4) Teste “CA errada” (deve falhar):

```powershell
Copy-Item .\mosquitto-ca.crt .\mosquitto-ca.BAD.crt
Add-Content .\mosquitto-ca.BAD.crt "corrupted"

python .\import_dataset.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.BAD.crt --mqtt-host localhost --mqtt-port 8883 --mqtt-username iot --mqtt-password iot --scenario fall_accident_001 --publish-truth-alerts
```

Resultado esperado:
- O script termina com erro de TLS (mensagem típica: `CERTIFICATE_VERIFY_FAILED`, `TLSV1_ALERT_UNKNOWN_CA` ou `handshake failure`).

Porquê:
- Esta é a prova prática de que existe validação de certificados: com uma CA incorreta/corrompida o cliente recusa a ligação, evitando ligar a um broker “falso” (man-in-the-middle) e evitando envio de dados para um endpoint não confiável.

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

# Enviar por MQTT (TLS) com telemetria em QoS 0
python import_dataset.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.crt --mqtt-host localhost --mqtt-port 8883 --mqtt-username iot --mqtt-password iot

# Opcional: publicar também os alertas esperados do truth.json em /bike/{id}/alert com QoS 1
python import_dataset.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.crt --mqtt-host localhost --mqtt-port 8883 --mqtt-username iot --mqtt-password iot --publish-truth-alerts
```

### 4. Validar Deteção nos Datasets
Compara os eventos esperados em `truth.json` com os alertas produzidos pelas regras do backend:

```powershell
python scripts\validate_braga_datasets.py --strict
```

### 5. Smoke Test da Stack
Com a stack Docker a correr, este teste verifica automaticamente backend, dashboard, REST, MQTT TLS, QoS 0/1, persistência no InfluxDB e endpoint de QoS. Se `.\mosquitto-ca.crt` ainda não existir, o script tenta exportar a CA do container `iot-mosquitto`.

```powershell
python scripts\smoke_test_stack.py
```

### 6. Simulação Contínua de Frota para Demo
Para a demonstração, usar a stack completa com o simulador dentro de Docker:

```powershell
docker compose up --build
```

Assim, o fluxo fica igual à arquitetura final: datasets -> simulador Docker -> Mosquitto MQTT TLS -> backend -> InfluxDB/dashboard/WebSocket.

O simulador mantém várias trotinetes e bicicletas ativas, escolhe aleatoriamente datasets de Braga, reescreve os timestamps para o momento atual e envia a telemetria para o backend.

```powershell
# Recomendado: via MQTT (TLS), com telemetria QoS 0 e alertas esperados QoS 1
python simulate_fleet.py --mode mqtt --mqtt-tls --mqtt-ca-cert .\mosquitto-ca.crt --mqtt-port 8883 --fleet-size 12 --speedup 5 --selection random --publish-truth-alerts

# Alternativa via REST
python simulate_fleet.py --mode rest --fleet-size 12 --speedup 5 --selection random --api-key iot
```

O simulador corre enquanto o Docker Compose estiver ativo. Com o compose atual, o MQTT externo está em `localhost:8883` (TLS). Por predefinição, as bicicletas publicam `dock_data_dump` quando chegam à estação final.

### 7. Testes Unitários e Latência de Alertas

```powershell
python -m unittest discover -s tests
python scripts\measure_alert_latency.py --api-key iot
```

O primeiro comando valida as regras de deteção. O segundo envia uma telemetria que gera `hard_brake` e mede o tempo até o alerta estar disponível na API.

### 8. Deploy Kubernetes

Os manifests em `k8s-manifests` criam namespace, Mosquitto autenticado, InfluxDB, backend e dashboard. Para a demo académica usam credenciais simples (`iot/iot` e `admin/adminadmin`). O Mosquitto em Kubernetes está configurado para MQTT sobre TLS na porta `8883`; o certificado self-signed é gerado no pod para simplificar a demonstração.

```powershell
docker build -t iot-backend:latest .\backend
docker build -t iot-dashboard:latest -f .\frontend\Dockerfile .
ansible-playbook -i ansible\inventory.ini ansible\deploy-manifests.yml
```

No dashboard Kubernetes, configurar a API por query string:

```text
http://<node-ip>:30081/?api_base=http://<node-ip>:30080/api/v1&ws_url=ws://<node-ip>:30080/ws/alerts&api_key=iot
```

### 9. Simular Alerta Manual
