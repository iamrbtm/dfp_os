from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import SlicerRuntime, get_slicer_runtime
from app.config import settings
from app.schemas.health import EngineHealth, HealthLiveResponse, HealthReadyResponse
from app.services.engines.base import EngineProbe

router = APIRouter(tags=["health"])
_LOGGER = logging.getLogger(__name__)


@router.get("/live", response_model=HealthLiveResponse)
async def health_live():
    return HealthLiveResponse(status="alive", service=settings.service_name)


@router.get("/ready", response_model=HealthReadyResponse)
async def health_ready(response: Response, runtime: SlicerRuntime = Depends(get_slicer_runtime)):
    probes = {engine_key: _probe_engine(engine_key, engine) for engine_key, engine in runtime.engines.items()}
    bambu_available = probes["bambu"].available
    prusa_available = probes["prusa"].available
    if bambu_available:
        mode = "primary"
    elif prusa_available:
        mode = "fallback_only"
    else:
        mode = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthReadyResponse(
        status="ready" if mode != "unhealthy" else "unhealthy",
        service=settings.service_name,
        mode=mode,
        engines={
            engine_key: EngineHealth(
                available=probe.available,
                version=probe.engine_version,
                error_code=None if probe.available else _stable_probe_code(probe.diagnostics.get("code")),
            )
            for engine_key, probe in probes.items()
        },
    )


def _stable_probe_code(value: object) -> str:
    if isinstance(value, str) and value in {
        "duplicate_profile",
        "executable_missing",
        "invalid_profile",
        "probe_failed",
        "probe_timeout",
        "profile_root_missing",
        "version_mismatch",
        "version_unrecognized",
    }:
        return value
    return "probe_failed"


def _probe_engine(engine_key: str, engine: object) -> EngineProbe:
    try:
        return engine.probe()
    except Exception:
        _LOGGER.exception("Slicer readiness probe failed for %s.", engine_key)
        return EngineProbe(
            engine_key=engine_key,
            engine_name="Bambu Studio" if engine_key == "bambu" else "PrusaSlicer",
            available=False,
            diagnostics={"code": "probe_failed"},
        )
