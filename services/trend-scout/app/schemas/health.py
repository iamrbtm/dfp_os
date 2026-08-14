from __future__ import annotations

from pydantic import BaseModel


class HealthLiveResponse(BaseModel):
    status: str
    service: str
    version: str


class HealthReadyResponse(BaseModel):
    status: str
    service: str
    database: str
    redis: str
    celery: str
    openai_configured: bool
