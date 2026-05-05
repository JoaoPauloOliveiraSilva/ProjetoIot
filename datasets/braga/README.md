# Braga Scooter Simulation Datasets

Datasets sinteticos para simular trotinetes em Braga, Portugal. As rotas foram geradas sobre geometria de ruas/ciclovias obtida do OpenStreetMap via Overpass API.

## Estrutura

Cada cenario tem:

- `telemetry.csv`: amostras temporais de telemetria.
- `truth.json`: eventos esperados para validacao.

O ficheiro `manifest.json` resume todos os cenarios gerados.

## Sensores Incluidos

Cada linha de telemetria inclui, no minimo, dados de 3 sensores:

- GPS: `lat`, `lon`, `speed`, `gps_accuracy_m`
- IMU: `accel_x`, `accel_y`, `accel_z`, `gyro_x`, `gyro_y`, `gyro_z`
- Ultrassom: `range_front_m`, `range_left_m`, `ultrasonic_valid`

## Cenarios

- `normal_001`: percurso normal, sem evento critico.
- `normal_stop_and_go_001`: percurso normal com paragens curtas.
- `normal_rough_pavement_001`: piso irregular sem acidente, util para testar falsos positivos.
- `hard_brake_001`: travagem brusca.
- `fall_accident_001`: queda/acidente com pico de aceleracao.
- `traffic_jam_001`: congestionamento prolongado.
- `mixed_brake_jam_001`: travagem brusca seguida de congestionamento.

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
