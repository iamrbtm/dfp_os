from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.database import check_db_connected
from app.schemas.health import HealthLiveResponse, HealthReadyResponse
from app.services.redis_streams import check_redis_connected

router = APIRouter(tags=["health"])


@router.get("/live", response_model=HealthLiveResponse)
async def health_live():
    return HealthLiveResponse(status="alive", service=settings.service_name)


@router.get("/ready", response_model=HealthReadyResponse)
async def health_ready():
    db_ok = await check_db_connected()
    resp = HealthReadyResponse(
        status="ready" if db_ok else "unhealthy",
        service=settings.service_name,
        database="connected" if db_ok else "disconnected",
    )
    if settings.use_redis_stream:
        redis_ok = await check_redis_connected()
        resp.redis = "connected" if redis_ok else "disconnected"
        if not redis_ok:
            resp.status = "unhealthy"
    if not db_ok:
        resp.status = "unhealthy"
    return resp
