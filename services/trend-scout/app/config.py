from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TREND_SCOUT_",
        extra="ignore",
    )

    service_env: str = "local"
    service_name: str = "dfp-trend-scout"
    api_host: str = "0.0.0.0"
    api_port: int = 8093

    database_url: str = "postgresql+asyncpg://dfp_trend_scout:change-me@localhost:5432/dfp_trend_scout"

    redis_url: str = "redis://redis:6379/2"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/1"

    internal_api_token: str = "change-me-local-token"

    audit_log_base_url: str = "http://audit-log:8090"
    audit_log_token: str = "change-me-audit-token"
    audit_log_enabled: bool = False

    openai_api_key: str = ""
    openai_model_trend_scout: str = "gpt-4o-mini"
    ai_provider: str = "openai"

    enable_redis_streams: bool = True
    stream_consumer_group: str = "trend_scout_workers"
    stream_batch_size: int = 100
    stream_block_ms: int = 2000
    stream_max_buffer: int = 10000

    celery_queue: str = "trend_scout"
    celery_task_priority: int = 1
    celery_default_priority: int = 5
    celery_max_priority: int = 10

    fetcher_pool_workers: int = 4
    fetcher_timeout_seconds: int = 30
    pipeline_soft_time_limit_seconds: int = 900
    pipeline_hard_time_limit_seconds: int = 960

    weights_default_seed_on_start: bool = True

    @property
    def celery_broker_url_full(self) -> str:
        return self.celery_broker_url

    @property
    def is_production(self) -> bool:
        return self.service_env.lower() in ("production", "prod", "release")


settings = Settings()
