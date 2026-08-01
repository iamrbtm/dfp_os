from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic

import httpx
import pytest

from app.api.dependencies import ReadinessProbeCache, get_slicer_runtime
from app.main import create_app
from app.services.engines.base import EngineProbe


@dataclass
class _Engine:
    probe_result: EngineProbe | BaseException
    calls: int = 0

    def probe(self) -> EngineProbe:
        self.calls += 1
        if isinstance(self.probe_result, BaseException):
            raise self.probe_result
        return self.probe_result


@dataclass
class _Runtime:
    engines: dict[str, _Engine]
    readiness: ReadinessProbeCache
    orchestrator: object | None = None


def _probe(engine_key: str, available: bool, *, version: str | None = None, code: str | None = None):
    return EngineProbe(
        engine_key=engine_key,
        engine_name="Bambu Studio" if engine_key == "bambu" else "PrusaSlicer",
        available=available,
        engine_version=version,
        diagnostics={"code": code} if code else {},
    )


@pytest.fixture(autouse=True)
def immediate_probe_thread_offload(monkeypatch: pytest.MonkeyPatch):
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("app.api.dependencies.asyncio.to_thread", run_inline)


async def _ready(bambu: EngineProbe | BaseException, prusa: EngineProbe | BaseException):
    app = create_app()

    async def runtime_override():
        return _Runtime(
            engines={"bambu": _Engine(bambu), "prusa": _Engine(prusa)},
            readiness=ReadinessProbeCache(ttl_seconds=5, timeout_seconds=0.1),
        )

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
async def test_required_profile_failure_keeps_stable_error_code_without_paths():
    response = await _ready(
        _probe("bambu", False, code="profile_missing"),
        _probe("prusa", True, version="2.8.1"),
    )

    assert response.status_code == 200
    assert response.json()["engines"]["bambu"]["error_code"] == "profile_missing"
    assert "path" not in response.text


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


@pytest.mark.asyncio
async def test_readiness_probes_engines_concurrently(monkeypatch: pytest.MonkeyPatch):
    active = 0
    max_active = 0

    async def concurrent_offload(function, *args, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        try:
            return function(*args, **kwargs)
        finally:
            active -= 1

    monkeypatch.setattr("app.api.dependencies.asyncio.to_thread", concurrent_offload)
    response = await _ready(
        _probe("bambu", True, version="2.7.1.62"),
        _probe("prusa", True, version="2.8.1"),
    )

    assert response.status_code == 200
    assert max_active == 2


@pytest.mark.asyncio
async def test_readiness_cache_avoids_reprobing_within_ttl():
    app = create_app()
    engines = {
        "bambu": _Engine(_probe("bambu", True, version="2.7.1.62")),
        "prusa": _Engine(_probe("prusa", True, version="2.8.1")),
    }
    runtime = _Runtime(
        engines=engines,
        readiness=ReadinessProbeCache(ttl_seconds=5, timeout_seconds=0.1),
    )

    async def runtime_override():
        return runtime

    app.dependency_overrides[get_slicer_runtime] = runtime_override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        first = await client.get("/health/ready")
        second = await client.get("/health/ready")

    assert first.status_code == second.status_code == 200
    assert engines["bambu"].calls == 1
    assert engines["prusa"].calls == 1


@pytest.mark.asyncio
async def test_readiness_total_budget_is_bounded_and_reports_probe_timeout(monkeypatch: pytest.MonkeyPatch):
    async def blocked_offload(_function, *_args, **_kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr("app.api.dependencies.asyncio.to_thread", blocked_offload)
    app = create_app()
    runtime = _Runtime(
        engines={
            "bambu": _Engine(_probe("bambu", True, version="2.7.1.62")),
            "prusa": _Engine(_probe("prusa", True, version="2.8.1")),
        },
        readiness=ReadinessProbeCache(ttl_seconds=5, timeout_seconds=0.05),
    )

    async def runtime_override():
        return runtime

    app.dependency_overrides[get_slicer_runtime] = runtime_override
    started = monotonic()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await asyncio.wait_for(client.get("/health/ready"), timeout=0.5)
    elapsed = monotonic() - started

    assert elapsed < 0.5
    assert response.status_code == 503
    assert response.json()["engines"]["bambu"]["error_code"] == "probe_timeout"
    assert response.json()["engines"]["prusa"]["error_code"] == "probe_timeout"
