import os
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

settings = Settings()