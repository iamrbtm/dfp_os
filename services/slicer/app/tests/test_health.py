from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app.api.dependencies import get_slicer_runtime
from app.main import create_app
from app.services.engines.base import EngineProbe


@dataclass
class _Engine:
    probe_result: EngineProbe | BaseException

    def probe(self) -> EngineProbe:
        if isinstance(self.probe_result, BaseException):
            raise self.probe_result
        return self.probe_result


@dataclass
class _Runtime:
    engines: dict[str, _Engine]
    orchestrator: object | None = None


def _probe(engine_key: str, available: bool, *, version: str | None = None, code: str | None = None):
    return EngineProbe(
        engine_key=engine_key,
        engine_name="Bambu Studio" if engine_key == "bambu" else "PrusaSlicer",
        available=available,
        engine_version=version,
        diagnostics={"code": code} if code else {},
    )


async def _ready(bambu: EngineProbe, prusa: EngineProbe):
    app = create_app()

    async def runtime_override():
        return _Runtime(engines={"bambu": _Engine(bambu), "prusa": _Engine(prusa)})

    app.dependency_overrides[get_slicer_runtime] = runtime_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get("/health/ready")


@pytest.mark.asyncio
async def test_bambu_available_reports_primary_mode():
    response = await _ready(
        _probe("bambu", True, version="2.7.1.62"),
        _probe("prusa", True, version="2.8.1"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "dfp-slicer",
        "mode": "primary",
        "engines": {
            "bambu": {"available": True, "version": "2.7.1.62", "error_code": None},
            "prusa": {"available": True, "version": "2.8.1", "error_code": None},
        },
    }


@pytest.mark.asyncio
async def test_only_prusa_available_reports_fallback_only_mode():
    response = await _ready(
        _probe("bambu", False, code="executable_missing"),
        _probe("prusa", True, version="2.8.1"),
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "fallback_only"
    assert response.json()["engines"]["bambu"] == {
        "available": False,
        "version": None,
        "error_code": "executable_missing",
    }


@pytest.mark.asyncio
async def test_no_engine_available_reports_unhealthy_with_503_and_stable_codes():
    response = await _ready(
        _probe("bambu", False, code="profile_root_missing"),
        _probe("prusa", False, code="probe_timeout"),
    )

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["mode"] == "unhealthy"
    assert response.json()["engines"] == {
        "bambu": {"available": False, "version": None, "error_code": "profile_root_missing"},
        "prusa": {"available": False, "version": None, "error_code": "probe_timeout"},
    }


@pytest.mark.asyncio
async def test_unknown_probe_diagnostic_is_not_exposed():
    response = await _ready(
        _probe("bambu", False, code="/private/path/secret"),
        _probe("prusa", True, version="2.8.1"),
    )

    assert response.status_code == 200
    assert response.json()["engines"]["bambu"]["error_code"] == "probe_failed"
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_unexpected_probe_exception_becomes_stable_unavailable_result():
    response = await _ready(
        RuntimeError("secret probe failure at /private/path"),
        _probe("prusa", False, code="executable_missing"),
    )

    assert response.status_code == 503
    assert response.json()["mode"] == "unhealthy"
    assert response.json()["engines"]["bambu"] == {
        "available": False,
        "version": None,
        "error_code": "probe_failed",
    }
    assert "private" not in response.text
