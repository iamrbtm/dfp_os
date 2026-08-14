"""End-to-end smoke tests for the Trend Scout microservice.

Verifies the integration surface at a few key boundaries. Real network /
DB / Celery / Firecrawl integrations are exercised in Phase 10.x follow-ups
against a docker-compose stack.
"""

from __future__ import annotations

import json

import pytest


def test_orchestration_modules_wire_correctly() -> None:
    """The orchestrator + analysis + sources + workers all import cleanly."""
    from app.compliance import gate_etsy_opt_in, is_acknowledgment_valid
    from app.services import (
        backtest,
        calibration,
        fetcher_pipeline,
        pipeline_runner,
    )
    from app.sources import firecrawl
    from app.workers import tasks

    assert fetcher_pipeline is not None
    assert backtest.run_backtest.__module__ == backtest.__name__
    assert calibration.run_calibration.__module__ == calibration.__name__
    assert pipeline_runner.run_full_pipeline.__module__ == pipeline_runner.__name__
    assert firecrawl.fetch_firecrawl_etsy is not None
    assert firecrawl.fetch_firecrawl_standard is not None
    assert tasks.trend_scout_pipeline is not None
    assert tasks.calibrate_trend_scout is not None
    assert callable(gate_etsy_opt_in)
    assert callable(is_acknowledgment_valid)


def test_fastapi_app_includes_every_router() -> None:
    """The Phase 5 FastAPI surface is still wired after Phase 6-9 changes."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        spec = client.get("/api/v1/openapi.json").json()

    paths = set(spec["paths"].keys())

    required = {
        "/health/live",
        "/api/v1/reports",
        "/api/v1/reports/latest",
        "/api/v1/opportunities",
        "/api/v1/source-health",
        "/api/v1/source-health/latest",
        "/api/v1/weights",
        "/api/v1/weights/defaults",
        "/api/v1/weights/save",
        "/api/v1/pipeline/run",
        "/api/v1/backtest/run",
        "/api/v1/calibration/run",
        "/api/v1/calibration/history",
        "/api/v1/settings/source-toggles",
    }
    missing = required - paths
    assert not missing, f"Missing routes: {missing}"


def test_celery_queue_partition_is_low_priority() -> None:
    """Phase 4 priority routing is still wired after Phase 6-9 changes."""
    from app.celery_app import celery

    queues = celery.conf.task_queues
    assert queues is not None
    trend_scout_q = next(q for q in queues if q.name == "trend_scout")
    assert trend_scout_q.queue_arguments["x-max-priority"] == 10

    routes = celery.conf.task_routes
    assert routes is not None
    matched = False
    for pattern, route in routes.items():
        if "app.workers.tasks" in pattern:
            assert route["queue"] == "trend_scout"
            assert route["priority"] == 1
            matched = True
    assert matched


def test_settings_exposes_etsy_compliance_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The compliance default path can be overridden for tests and CLI runs."""
    import importlib

    from app import compliance as compliance_module

    importlib.reload(compliance_module)
    monkeypatch.setattr(
        compliance_module,
        "default_compliance_path",
        lambda: tmp_path / "etsy_opt_in.json",
    )
    assert compliance_module.default_compliance_path() == tmp_path / "etsy_opt_in.json"


def test_serialization_roundtrip_compliance_payload(tmp_path) -> None:
    """The acknowledgment file is JSON with the expected keys."""
    from app.compliance import record_acknowledgment

    target = tmp_path / "etsy_opt_in.json"
    record_acknowledgment(path=target, note="phase 10 smoke", operator="tester")
    payload = json.loads(target.read_text())
    assert payload["note"] == "phase 10 smoke"
    assert payload["operator"] == "tester"
    assert "acknowledged_at" in payload
    assert "acknowledged_legal_posture" in payload


def test_internal_demand_source_uses_proxy() -> None:
    """The internal_demand fetcher looks at TREND_SCOUT_FLASK_INTERNAL_TOKEN / BASE_URL."""
    import inspect

    from app.sources.internal_demand import fetch_internal_demand

    sig = inspect.signature(fetch_internal_demand)
    params = list(sig.parameters.keys())
    assert "flask_base_url" in params
    assert "flask_token" in params


def test_firecrawl_target_matrix_matches_plan() -> None:
    """The Firecrawl standard tier + Etsy + fallback are all registered."""
    from app.sources.firecrawl import (
        ETSY_TARGET,
        TARGETS,
        fetch_firecrawl_etsy,
        fetch_firecrawl_mmf_fallback,
        fetch_firecrawl_standard,
    )

    expected_keys = {
        "cults3d",
        "thangs",
        "stlfinder",
        "cgtrader",
        "mmf_trending",
        "general",
    }
    assert set(TARGETS.keys()) == expected_keys
    assert ETSY_TARGET.key == "etsy"
    assert ETSY_TARGET.throttled is True
    assert ETSY_TARGET.require_explicit_opt_in is True
    assert callable(fetch_firecrawl_standard)
    assert callable(fetch_firecrawl_mmf_fallback)
    assert callable(fetch_firecrawl_etsy)


def test_firecrawl_target_mm_fallback_only() -> None:
    """mmf_trending is the only fallback_only target."""
    from app.sources.firecrawl import TARGETS

    fallbacks = [k for k, v in TARGETS.items() if v.fallback_only]
    assert fallbacks == ["mmf_trending"]


def test_source_weights_include_firecrawl_targets() -> None:
    """DEFAULT_SOURCE_WEIGHTS covers all 7 firecrawl targets."""
    from app.services import weights

    for key in (
        "firecrawl_etsy",
        "firecrawl_cults3d",
        "firecrawl_thangs",
        "firecrawl_stlfinder",
        "firecrawl_cgtrader",
        "firecrawl_mmf",
        "firecrawl_general",
    ):
        assert key in weights.DEFAULT_SOURCE_WEIGHTS


def test_db_models_table_names() -> None:
    """Phase 1 migration created the 5 expected tables."""
    from app.models import (
        SourceHealthRecord,
        TrendOpportunityScore,
        TrendReport,
        TrendSnapshot,
        TrendWeight,
    )

    assert TrendSnapshot.__tablename__ == "trend_snapshots"
    assert TrendReport.__tablename__ == "trend_reports"
    assert TrendOpportunityScore.__tablename__ == "trend_opportunity_scores"
    assert SourceHealthRecord.__tablename__ == "source_health_records"
    assert TrendWeight.__tablename__ == "trend_weights"


@pytest.mark.asyncio
async def test_audit_dispatch_respects_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit dispatch is a no-op when audit_log_enabled is False."""
    from app.config import settings as app_settings
    from app.services import audit_dispatch

    monkeypatch.setattr(app_settings, "audit_log_enabled", False)
    ok = await audit_dispatch.dispatch_audit_event(
        action="trend_scout.smoke.no_op",
        entity_type="smoke",
        entity_id="1",
    )
    assert ok is False


def test_firecrawl_vendored_client_files_exist() -> None:
    """The vendored Firecrawl client lives at the expected path."""
    from pathlib import Path

    here = Path(__file__).resolve()
    repo_root = here.parents[4]
    for relpath in (
        "services/firecrawl/firecrawl_client.py",
        "services/firecrawl/README.md",
        "services/firecrawl/UPSTREAM_LOCK.json",
    ):
        assert (repo_root / relpath).exists(), f"{relpath} not found"
