from pydantic import BaseModel


class HealthLiveResponse(BaseModel):
    status: str
    service: str


class HealthReadyResponse(BaseModel):
    status: str
    service: str
    database: str
    redis: str | None = None
