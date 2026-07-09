from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INTELLIGENCE_", extra="ignore")

    service_env: str = "local"
    service_name: str = "dfp-intelligence"
    api_host: str = "0.0.0.0"
    api_port: int = 8091

    database_url: str = "postgresql+asyncpg://dfp_intelligence:dfp_intelligence_password@localhost:5433/dfp_intelligence"
    internal_api_token: str = "change-me-local-token"

    audit_log_base_url: str = "http://localhost:8090"
    audit_log_token: str = "change-me-audit-token"
    audit_log_enabled: bool = False

    legacy_mariadb_host: str | None = None
    legacy_mariadb_port: int = 3306
    legacy_mariadb_database: str | None = None
    legacy_mariadb_user: str | None = None
    legacy_mariadb_password: str | None = None
    legacy_mariadb_connect_timeout: int = 10


settings = Settings()
