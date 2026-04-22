import csv
import json
import requests
import os
import glob
import sys
from datetime import datetime, timezone

API_URL = "http://127.0.0.1:8000/api/v1/sensors"
API_KEY = "SeiLa"
# Caminho padrão (pode ser sobrescrito via argumento de linha de comando)
DEFAULT_DATASET_PATH = r"C:\Users\38240\Downloads\Bike&Safe Dataset\Bike&Safe Dataset\Bike&Safe Dataset"

def process_lap(route_name, lap_name, path):
    print(f"Processing {route_name} - {lap_name}...")
    
    # Files
    gps_files = glob.glob(os.path.join(path, "*GPS*.csv"))
    accel_files = glob.glob(os.path.join(path, "*accelerometer*.csv"))
    
    if not gps_files or not accel_files:
        print(f"Skipping {route_name} {lap_name}: Files not found em {path}")
        return

    gps_file = gps_files[0]
    accel_file = accel_files[0]
    
    # Read GPS data
    gps_data = []
    with open(gps_file, 'r') as f:
        # Use comma as default, but try semicolon if no data found
        content = f.read()
        f.seek(0)
        delimiter = ';' if ';' in content.split('\n')[0] else ','
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row or row[0] != "GPS": continue
            try:
                gps_data.append({
                    "lat": float(row[1]),
                    "lon": float(row[2]),
                    "speed": float(row[3]) * 3.6, # Convert m/s to km/h
                    "timestamp_ms": int(float(row[4]))
                })
            except: continue

    # Read Accel data
    accel_data = []
    with open(accel_file, 'r') as f:
        content = f.read()
        f.seek(0)
        delimiter = ';' if ';' in content.split('\n')[0] else ','
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row: continue
            try:
                accel_data.append({
                    "timestamp_ns": int(row[0]),
                    "x": float(row[2]),
                    "y": float(row[3]),
                    "z": float(row[5])
                })
            except: continue

    # Merge and Send
    device_id = f"bike_{route_name.lower().replace(' ', '_')}_{lap_name.lower().replace(' ', '_')}"
    
    count = 0
    for gps in gps_data:
        dt = datetime.fromtimestamp(gps['timestamp_ms'] / 1000.0, tz=timezone.utc)
        
        payload = {
            "device_id": device_id,
            "timestamp": dt.isoformat(),
            "lat": gps['lat'],
            "lon": gps['lon'],
            "speed": gps['speed'],
            "battery": 100,
            "rssi": -50,
            "gps_quality": 1,
            "source": "dataset_import",
            "type": "telemetry",
            "accel_x": accel_data[count % len(accel_data)]['x'] if accel_data else 0,
            "accel_y": accel_data[count % len(accel_data)]['y'] if accel_data else 0,
            "accel_z": accel_data[count % len(accel_data)]['z'] if accel_data else 0
        }
        
        try:
            resp = requests.post(API_URL, json=payload, headers={"X-API-Key": API_KEY})
            if resp.status_code == 200:
                count += 1
        except Exception as e:
            print(f"Error sending data: {e}")
            
    print(f"Imported {count} points for {device_id}")

def main():
    # Verifica se um caminho foi passado via argumento
    dataset_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATASET_PATH
    
    if not os.path.exists(dataset_path):
        print(f"Erro: O caminho do dataset não existe: {dataset_path}")
        print("Uso: python import_dataset.py \"C:\\caminho\\para\\o\\dataset\"")
        return

    routes = ["First route", "Second route", "Third route"]
    laps = ["First lap", "Second lap", "Third lap"]
    
    for r in routes:
        for l in laps:
            path = os.path.join(dataset_path, r, l)
            if os.path.exists(path):
                process_lap(r, l, path)
            else:
                print(f"Aviso: Subpasta não encontrada: {path}")

if __name__ == "__main__":
    main()
