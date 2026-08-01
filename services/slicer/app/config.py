from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


MIN_INTERNAL_API_TOKEN_BYTES = 24
_TOKEN_PLACEHOLDER_MARKERS = ("changeme", "replacewith")


def is_valid_internal_api_token(value: object) -> bool:
    if not isinstance(value, str) or len(value) < MIN_INTERNAL_API_TOKEN_BYTES:
        return False
    normalized = "".join(character for character in value.lower() if character.isalnum())
    if value != value.strip() or any(marker in normalized for marker in _TOKEN_PLACEHOLDER_MARKERS):
        return False
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return all(0x21 <= byte <= 0x7E for byte in encoded)


def _valid_config_string(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    return all(character.isprintable() and ord(character) < 128 for character in value)


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
    slice_timeout_seconds: int = Field(default=600, ge=2)
    max_concurrent_slices: int = Field(default=2, ge=1, le=16)
    readiness_timeout_seconds: int = Field(default=4, ge=1, le=8)
    readiness_cache_ttl_seconds: int = Field(default=5, ge=1, le=60)
    metadata_header_max_bytes: int = Field(default=6144, ge=1)
    max_model_bytes: int = Field(default=268435456, ge=1)
    internal_api_token: str = "replace-with-a-random-32-byte-token"
    log_level: str = "INFO"

    def validate_for_startup(self) -> None:
        if not is_valid_internal_api_token(self.internal_api_token):
            raise ValueError(
                f"SLICER_INTERNAL_API_TOKEN must be at least {MIN_INTERNAL_API_TOKEN_BYTES} printable ASCII bytes "
                "and must not be a placeholder."
            )
        if self.engine_order != "bambu,prusa":
            raise ValueError("SLICER_ENGINE_ORDER must be exactly 'bambu,prusa'.")
        if not _valid_config_string(self.bambu_studio_path) or not Path(self.bambu_studio_path).is_absolute():
            raise ValueError("SLICER_BAMBU_STUDIO_PATH must be a printable absolute path.")
        if not _valid_config_string(self.bambu_profile_root) or not Path(self.bambu_profile_root).is_absolute():
            raise ValueError("SLICER_BAMBU_PROFILE_ROOT must be a printable absolute path.")
        if not _valid_config_string(self.prusa_slicer_path):
            raise ValueError("SLICER_PRUSA_SLICER_PATH must be a printable command or path.")


settings = Settings()
