import json
import paho.mqtt.client as mqtt
from app.core.config import settings
from app.database import influx_db
from app.models.sensor import SensorData
from app.models.alert import AlertData
import ssl


def on_connect(client,userdata,flags,rc):
    if rc == 0:
        print(f" Ligado ao broker MQTT em {settings.MQTT_BROKER}:{settings.MQTT_PORT} (TLS: {settings.MQTT_TLS_ENABLED})")  
        client.subscribe("/bike/+/telemetry",qos = 0)
        client.subscribe("/bike/+/alerts",qos=1)
        print("A escutar")
    else:
        print(f"Falha ao conectar ao mqtt: {rc}")    



def on_disconnect(client,userdata,rc):
    if rc!=0:
        print("Desligado do mqtt")


def on_message(client,userdata,msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8') 
    
    try:
        data_dict = json.loads(payload)
        
        if topic.endswith("/telemetry"):
            sensor_data = SensorData(**data_dict)
            influx_db.save_sensor_data(sensor_data)
        elif topic.endswith("/alerts"):
            alert_data = AlertData(**data_dict)
            influx_db.save_alert_data(alert_data)
    except json.JSONDecodeError:
        print ("Parsion error: o Json recebiso nao é valido")
    except Exception as e:
        print (f"Erro ao processar a mensagem do topico {e}")    

mqtt_client = mqtt.Client()

if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
    mqtt_client.username_pw_set(settings.MQTT_USERNAME,settings.MQTT_PASSWORD)

if settings.MQTT_TLS_ENABLED:
    mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED,tls_version=ssl.PROTOCOL_TLS) 

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect= on_disconnect
mqtt_client.on_message = on_message


def start_mqtt():
    try:
        mqtt_client.connect(settings.MQTT_BROKER, settings.MQTT_PORT,60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"Erro ao iniciar o mqtt {e}")


def stop_mqtt():
    mqtt_client.loop.stop()
    mqtt_client.disconnect()            
      