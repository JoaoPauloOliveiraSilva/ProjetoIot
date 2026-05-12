from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    INFLUX_TOKEN: str
    INFLUX_ORG: str
    INFLUX_BUCKET: str = "Iot"
    API_KEY_EDGE: str
    INFLUX_URL: str
        
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 8883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_TLS_ENABLED: bool = True
    MQTT_TLS_CA_CERT: str = ""
    MQTT_TLS_INSECURE: bool = False
    
    THRESHOLD_FALL_ACCEL: float = 20.0  
    THRESHOLD_HARD_BRAKE: float = -6.0  
    THRESHOLD_JAM_SPEED: float = 2.0    
    THRESHOLD_OBSTACLE_FRONT_M: float = 0.45
    THRESHOLD_OBSTACLE_SPEED: float = 6.0
    JAM_TIME_WINDOW_SEC: int = 60
    JAM_MIN_CONSECUTIVE_SAMPLES: int = 60
    ALERT_COOLDOWN_SEC: int = 15
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
