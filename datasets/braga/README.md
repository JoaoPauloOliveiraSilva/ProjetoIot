# Braga Micromobility Simulation Datasets

Datasets sinteticos para simular trotinetes e bicicletas em Braga, Portugal. As rotas foram geradas sobre geometria de ruas/ciclovias obtida do OpenStreetMap via Overpass API.

## Estrutura

Cada cenario tem:

- `telemetry.csv`: amostras temporais de telemetria.
- `truth.json`: eventos esperados para validacao.

O ficheiro `manifest.json` resume todos os 100 cenarios gerados: 50 de trotinetes e 50 de bicicletas.

## Sensores Incluidos

Cada linha de telemetria inclui, no minimo, dados de 3 sensores:

- GPS: `lat`, `lon`, `speed`, `gps_accuracy_m`
- IMU: `accel_x`, `accel_y`, `accel_z`, `gyro_x`, `gyro_y`, `gyro_z`
- Ultrassom: `range_front_m`, `range_left_m`, `ultrasonic_valid`

Os cenarios de bicicleta incluem tambem:

- `vehicle_type=bicycle`
- `start_station_id`, `start_station_name`
- `end_station_id`, `end_station_name`
- `dock_status` e `charging`

No fim da viagem, a bicicleta fica parada na estacao final durante algumas amostras com `charging=true`. O simulador usa estes metadados para publicar o evento operacional `dock_data_dump`, que resume se a descarga de dados foi completa. Todos os cenarios de bicicleta começam numa estacao e acabam numa estacao, podendo ser a mesma.

## Cenarios

O conjunto combina percursos normais, travagens bruscas, quedas/acidentes, congestionamentos, risco de obstaculo por ultrassom e cenarios mistos. Os nomes abaixo mostram as familias principais; as variantes numeradas completam as 50 rotas de cada veiculo.

### Trotinetes

- `normal_001`: percurso normal, sem evento critico.
- `normal_stop_and_go_001`: percurso normal com paragens curtas.
- `normal_rough_pavement_001`: piso irregular sem acidente, util para testar falsos positivos.
- `hard_brake_001`: travagem brusca.
- `fall_accident_001`: queda/acidente com pico de aceleracao.
- `traffic_jam_001`: congestionamento prolongado.
- `obstacle_risk_001`: obstaculo proximo detetado por ultrassom.
- `mixed_brake_jam_001`: travagem brusca seguida de congestionamento.

### Bicicletas

- `bike_normal_center_001`: percurso normal no centro, com docking no fim.
- `bike_commute_center_002`: deslocacao curta entre estacoes centrais.
- `bike_evening_return_003`: regresso de fim de tarde.
- `bike_hard_brake_center_001`: travagem brusca.
- `bike_fall_accident_center_001`: queda/acidente.
- `bike_traffic_jam_center_001`: congestionamento.
- `bike_obstacle_risk_center_001`: obstaculo proximo.
- `bike_mixed_brake_jam_center_001`: travagem brusca seguida de congestionamento.

## Regenerar

```powershell
python scripts\generate_braga_datasets.py
```

Para forcar novo download de dados OSM:

```powershell
python scripts\generate_braga_datasets.py --force-osm
```

## Atribuicao

Dados de ruas derivados de OpenStreetMap. Atribuicao: OpenStreetMap contributors.
