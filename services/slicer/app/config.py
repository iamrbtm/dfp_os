from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SLICER_", extra="ignore")

    service_env: str = "local"
    service_name: str = "dfp-slicer"
    api_host: str = "0.0.0.0"
    api_port: int = 8092

    prusa_slicer_path: str = "prusa-slicer"
    internal_api_token: str = "change-me-slicer-token"
    log_level: str = "INFO"


settings = Settings()
