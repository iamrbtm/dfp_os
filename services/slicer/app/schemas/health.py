from __future__ import annotations

from pydantic import BaseModel


class HealthLiveResponse(BaseModel):
    status: str
    service: str


class EngineHealth(BaseModel):
    available: bool
    version: str | None = None
    error_code: str | None = None


class HealthReadyResponse(BaseModel):
    status: str
    service: str
    mode: str
    engines: dict[str, EngineHealth]
