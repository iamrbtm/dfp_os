from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUDIT_", extra="ignore")

    service_env: str = "local"
    service_name: str = "dfp-audit-log"
    api_host: str = "0.0.0.0"
    api_port: int = 8090

    database_url: str = "postgresql+asyncpg://dfp_audit:dfp_audit_password@localhost:5432/dfp_audit"
    redis_url: str = "redis://localhost:6379/0"

    internal_api_token: str = "change-me-local-token"
    hash_secret: str = "change-me-local-hash-secret"

    use_redis_stream: bool = False
    stream_name: str = "dfp.audit.events"
    stream_consumer_group: str = "audit-log-writers"
    stream_consumer_name: str = "audit-worker-1"

    log_level: str = "INFO"


settings = Settings()
