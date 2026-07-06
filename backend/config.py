from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ─── Database ───
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "agentmint"
    db_user: str = "agentmint"
    db_password: str = "agentmint_dev"

    # ─── Redis ───
    redis_host: str = "localhost"
    redis_port: int = 6379

    # ─── JWT ───
    jwt_secret: str = "agentmint-dev-secret-change-in-production-64chars"
    jwt_expiry_hours: int = 24
    jwt_refresh_expiry_days: int = 30

    # ─── SMS ───
    sms_provider: str = "mock"  # mock | aliyun
    sms_sign_name: str = "Agent竞技场"
    sms_template_code: str = "SMS_123456789"
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""

    # ─── File storage ───
    public_api_base_url: str = "http://localhost:8000"
    file_store: str = "minio"  # minio | oss
    minio_endpoint: str = "http://localhost:9000"
    minio_public_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "agentmint-files"
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""

    # ─── CORS ───
    allowed_origins: list[str] = ["http://localhost:3000"]

    # ─── WS heartbeat ───
    ws_heartbeat_interval_ms: int = 30000
    ws_heartbeat_timeout_seconds: int = 90

    # ─── Reward maintenance ───
    reward_maintenance_enabled: bool = True
    reward_maintenance_interval_seconds: int = 300


settings = Settings()
