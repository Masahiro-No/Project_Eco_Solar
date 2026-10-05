import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT_DIR, ".env")

class Settings(BaseSettings):
    """Application settings."""
    # ระบุ env_file เป็น ENV_PATH แทนการใช้แค่ ".env"
    APP_NAME: str = "FastAPI Application"
    DEBUG_MODE: bool = True
    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf-8")

    database_url: str
    label_studio_url: str
    label_studio_api_key: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    redis_host: str = "localhost"
    redis_port: int = 6379
    enable_retrain: bool = False
    retrain_debounce_seconds: int = 300  # รอรวม label ที่ส่งใกล้กันก่อนเริ่ม retrain
    convlstm_retrain_threshold: int = 50  # new daytime satellite scans that make one ConvLSTM retrain batch
    mlflow_tracking_uri: str = "http://mlflow:5000"  # retrain history shown on the admin page
    # admin account created at startup when a password is configured (ADMIN_PASSWORD in the root .env)
    admin_email: str = "admin@solardss.io"
    admin_password: Optional[str] = None

settings = Settings()