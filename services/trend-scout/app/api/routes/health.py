from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, check_db_connected
from app.schemas.health import HealthLiveResponse, HealthReadyResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

SERVICE_VERSION = "0.1.0"


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@router.get("/live", response_model=HealthLiveResponse)
async def health_live() -> HealthLiveResponse:
    return HealthLiveResponse(
        status="alive",
        service=settings.service_name,
        version=SERVICE_VERSION,
    )


async def _check_redis() -> str:
    try:
        import redis.asyncio as redis_async

        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.ping()
            return "connected"
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return "disconnected"


async def _check_celery() -> str:
    try:
        from app.celery_app import celery

        result = celery.control.ping(timeout=2.0)
        return "reachable" if result else "no_workers"
    except Exception as exc:
        logger.warning("Celery health check failed: %s", exc)
        return "unreachable"


@router.get("/ready", response_model=HealthReadyResponse)
async def health_ready() -> HealthReadyResponse:
    db_ok = await check_db_connected()
    redis_status = await _check_redis()
    celery_status = await _check_celery()
    openai_configured = bool(settings.openai_api_key)
    overall = "ready" if db_ok and redis_status == "connected" else "unhealthy"
    return HealthReadyResponse(
        status=overall,
        service=settings.service_name,
        database="connected" if db_ok else "disconnected",
        redis=redis_status,
        celery=celery_status,
        openai_configured=openai_configured,
    )


@router.get("/deep", response_model=HealthReadyResponse)
async def health_deep(db: AsyncSession = Depends(get_db)) -> HealthReadyResponse:
    """Deep health check: verifies DB, Redis, Celery, and OpenAI config.

    Used for readiness probes and CI smoke tests. The HTTP code remains 200
    regardless of degraded dependencies so a single bad dependency does not
    break orchestrator probes that only check the status code. Inspect the
    per-dependency fields for actual health.
    """
    db_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        db_ok = result.scalar() == 1
    except Exception as exc:
        logger.warning("Deep DB health check failed: %s", exc)

    redis_status = await _check_redis()
    celery_status = await _check_celery()
    openai_configured = bool(settings.openai_api_key)
    overall = "ready" if db_ok and redis_status == "connected" else "degraded"
    return HealthReadyResponse(
        status=overall,
        service=settings.service_name,
        database="connected" if db_ok else "disconnected",
        redis=redis_status,
        celery=celery_status,
        openai_configured=openai_configured,
    )


@router.get("/ping")
async def health_ping() -> dict[str, str]:
    """Trivial ping for load balancers that only need a 200."""
    return {"status": "ok"}
