from __future__ import annotations

import subprocess

from fastapi import APIRouter

from app.config import settings
from app.schemas.health import HealthLiveResponse, HealthReadyResponse

router = APIRouter(tags=["health"])


@router.get("/live", response_model=HealthLiveResponse)
async def health_live():
    return HealthLiveResponse(status="alive", service=settings.service_name)


@router.get("/ready", response_model=HealthReadyResponse)
async def health_ready():
    prusa_bin = settings.prusa_slicer_path

    try:
        check = subprocess.run(
            [prusa_bin, "--help-fff"],
            capture_output=True,
            timeout=10,
        )
        prusa_ok = check.returncode == 0
    except Exception:
        prusa_ok = False

    return HealthReadyResponse(
        status="ready" if prusa_ok else "unhealthy",
        service=settings.service_name,
        prusa_slicer="available" if prusa_ok else "not_found",
    )
