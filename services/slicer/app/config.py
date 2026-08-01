from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SLICER_", extra="ignore")

    service_env: str = "local"
    service_name: str = "dfp-slicer"
    api_host: str = "0.0.0.0"
    api_port: int = 8092

    bambu_studio_path: str = "/opt/bambu-studio/AppRun"
    bambu_profile_root: str = "/opt/bambu-studio/resources/profiles/BBL"
    prusa_slicer_path: str = "prusa-slicer"
    engine_order: str = "bambu,prusa"
    slice_timeout_seconds: int = Field(default=600, ge=1)
    metadata_header_max_bytes: int = Field(default=6144, ge=1)
    max_model_bytes: int = Field(default=268435456, ge=1)
    internal_api_token: str = "change-me-slicer-token"
    log_level: str = "INFO"


settings = Settings()
