"""Tests for Phase 5: FastAPI surface (reports, opportunities, source-health, weights, pipeline, settings)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TREND_SCOUT_SERVICE_ENV", "testing")
    monkeypatch.setenv("TREND_SCOUT_INTERNAL_API_TOKEN", "test-token-phase5")
    monkeypatch.setenv("TREND_SCOUT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("TREND_SCOUT_REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("TREND_SCOUT_CELERY_BROKER_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("TREND_SCOUT_CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    monkeypatch.setenv("TREND_SCOUT_AUDIT_LOG_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_security_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ``app.security.settings`` (the global instance) has the test token.

    ``app.security`` reads ``settings`` at the module level via ``from app.config
    import settings``. The instance is created on first import. When monkeypatch
    runs ``setenv`` later, that doesn't reset the global instance's
    ``internal_api_token``. Force the field to match this test run.
    """
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "internal_api_token", "test-token-phase5")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token-phase5"}


def _session_factory():
    """Return an async session factory that yields a mocked AsyncSession."""
    from app.database import async_session_factory as real_factory

    return real_factory


def test_openapi_lists_all_resources() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    body = response.json()
    paths = body["paths"].keys()
    expected_paths = {
        "/api/v1/reports",
        "/api/v1/reports/latest",
        "/api/v1/opportunities",
        "/api/v1/source-health",
        "/api/v1/source-health/latest",
        "/api/v1/weights",
        "/api/v1/weights/defaults",
        "/api/v1/weights/save",
        "/api/v1/pipeline/run",
        "/api/v1/pipeline/status/{run_id}",
        "/api/v1/backtest/run",
        "/api/v1/calibration/run",
        "/api/v1/calibration/history",
        "/api/v1/settings/source-toggles",
    }
    assert expected_paths.issubset(set(paths))


def test_unauthorized_requests_are_rejected() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/reports", headers={})
    assert response.status_code in (401, 403)


def test_wrong_token_is_rejected() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/reports",
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401


def test_health_endpoints_public() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        for path in ("/health/live", "/health/ping"):
            response = client.get(path)
        assert response.status_code == 200


def test_reports_endpoint_handles_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DB is unreachable, /api/v1/reports returns 5xx not a crash."""
    from app.api.routes import reports as reports_route
    from app.main import create_app

    class _BoomSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("db unreachable")

        async def commit(self):
            return None

    def boom_factory():
        return _BoomSession()

    monkeypatch.setattr(reports_route, "async_session_factory", boom_factory)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/reports", headers=_auth_headers())
    assert response.status_code in (500, 503)


def test_weights_defaults_endpoint_returns_four_groups() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/weights/defaults", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert "score" in body
    assert "source" in body
    assert "buyer" in body
    assert "metric" in body
    assert "source_enabled" in body
    assert "firecrawl_etsy" in body["source"]
    assert body["source"]["firecrawl_etsy"] <= body["source"]["firecrawl_cults3d"]


def test_pipeline_run_returns_202(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import pipeline as pipeline_route
    from app.main import create_app

    fake_async_result = MagicMock()
    fake_async_result.id = "fake-task-id"

    monkeypatch.setattr(
        pipeline_route.celery,
        "send_task",
        lambda *args, **kwargs: fake_async_result,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/pipeline/run",
            json={"trigger": "test"},
            headers=_auth_headers(),
        )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["status"] == "queued"
    assert body["task_id"] == "fake-task-id"
    assert body["run_id"].startswith("run-")


def test_pipeline_status_unknown_when_run_not_found() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/pipeline/status/no-such-run",
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "unknown"


def test_pipeline_run_is_visible_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import pipeline as pipeline_route
    from app.main import create_app
    from app.workers import task_monitor

    task_monitor._task_runs.clear()
    monkeypatch.setattr(task_monitor, "_redis_client", None)

    fake_async_result = MagicMock()
    fake_async_result.id = "celery-visible-1"
    monkeypatch.setattr(pipeline_route.celery, "send_task", lambda *args, **kwargs: fake_async_result)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/pipeline/run",
            json={"trigger": "manual", "run_id": "run-visible-1"},
            headers=_auth_headers(),
        )
        assert response.status_code == 202

        status_response = client.get(
            "/api/v1/pipeline/status/run-visible-1",
            headers=_auth_headers(),
        )
        detail_by_run = client.get(
            "/api/v1/pipeline/runs/run-visible-1",
            headers=_auth_headers(),
        )
        detail_by_task = client.get(
            "/api/v1/pipeline/runs/celery-visible-1",
            headers=_auth_headers(),
        )

    assert status_response.status_code == 200
    assert status_response.json()["state"] == "queued"
    assert status_response.json()["progress"] == 0.0
    assert detail_by_run.status_code == 200
    assert detail_by_task.status_code == 200
    assert detail_by_run.json() == detail_by_task.json()
    assert detail_by_run.json()["task_id"] == "celery-visible-1"


def test_pipeline_cancel_updates_known_run_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import pipeline as pipeline_route
    from app.main import create_app
    from app.workers import task_monitor

    task_monitor._task_runs.clear()
    monkeypatch.setattr(task_monitor, "_redis_client", None)
    task_monitor.create_task_run(
        "celery-cancel-1",
        trigger="manual",
        total_steps=12,
        run_id="run-cancel-1",
    )

    revoked: list[str] = []
    monkeypatch.setattr(
        pipeline_route.celery.control,
        "revoke",
        lambda task_id, terminate=False: revoked.append(task_id),
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/pipeline/cancel/run-cancel-1",
            headers=_auth_headers(),
        )
        detail = client.get(
            "/api/v1/pipeline/runs/run-cancel-1",
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert revoked == ["celery-cancel-1"]
    assert detail.json()["status"] == "revoked"


def test_calibration_run_returns_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import backtest as backtest_route
    from app.main import create_app

    async def fake_run_calibration(session, trigger="manual", **kwargs):
        return {"status": "ok", "trigger": trigger, "summary": {"mae": 0.1}}

    async def fake_get_history(session, limit=20):
        return []

    class _NoopSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    def fake_factory():
        return _NoopSession()

    monkeypatch.setattr(backtest_route, "async_session_factory", fake_factory)
    # Patch on the route's local binding so the override is used.
    monkeypatch.setattr(backtest_route, "calibration_service", fake_run_calibration)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/calibration/run",
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_backtest_run_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import backtest as backtest_route
    from app.main import create_app

    async def fake_run_backtest(session, **kwargs):
        return {"status": "no_data", "report_count": 0, "summary": {}}

    class _NoopSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    def fake_factory():
        return _NoopSession()

    monkeypatch.setattr(backtest_route, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(backtest_route, "async_session_factory", fake_factory)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backtest/run",
            json={"lookback_reports": 12, "sales_window_days": 60},
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    assert response.json()["status"] == "no_data"


def test_settings_source_toggle_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import settings as settings_route
    from app.main import create_app

    saved: list[Any] = []

    async def fake_save(session, group, key, value, description=None):
        saved.append((group, key, value))

    class _CommitSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def commit(self):
            return None

    def fake_factory():
        return _CommitSession()

    monkeypatch.setattr(settings_route.weights_service, "save_weight", fake_save)
    monkeypatch.setattr(settings_route, "async_session_factory", fake_factory)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/settings/source-toggles",
            json={"source": "etsy", "enabled": False},
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    assert saved and saved[0][0] == "source_enabled"
    assert saved[0][2] == 0.0


def test_opportunities_action_rejects_unknown_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the opportunity exists but the action is invalid, return 422."""

    from app.api.routes import opportunities as opportunities_route
    from app.main import create_app

    class _StubRow:
        id = 1
        report_id = 1
        keyword = "dragon"
        source = "etsy"
        score = 80.0
        recommended_action = "print_now"
        velocity = 0.5
        momentum = 0.5
        purchase_intent = 0.5
        license_risk = "low"
        local_relevance = 0.5
        dismissed = False
        score_breakdown = {}

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _StubRow()

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    def fake_factory():
        return _Session()

    monkeypatch.setattr(opportunities_route, "async_session_factory", fake_factory)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/opportunities/1/action",
            json={"action": "explode"},
            headers=_auth_headers(),
        )
    assert response.status_code == 422


def test_opportunities_action_accepts_valid_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the model exists, the action update succeeds and returns the row."""

    from app.api.routes import opportunities as opportunities_route
    from app.main import create_app

    class _TrendOpportunityScoreStub:
        id = 1
        report_id = 1
        keyword = "dragon"
        source = "etsy"
        score = 80.0
        recommended_action = "print_now"
        velocity = 0.5
        momentum = 0.5
        purchase_intent = 0.5
        license_risk = "low"
        local_relevance = 0.5
        dismissed = False
        score_breakdown = {}

    stub = _TrendOpportunityScoreStub()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return stub

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    def fake_factory():
        return _Session()

    monkeypatch.setattr(opportunities_route, "async_session_factory", fake_factory)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/opportunities/1/action",
            json={"action": "watch"},
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["keyword"] == "dragon"


def test_pipeline_cancel_returns_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import pipeline as pipeline_route
    from app.main import create_app

    fake_control = MagicMock()
    fake_control.revoke = MagicMock(return_value=None)
    monkeypatch.setattr(pipeline_route.celery, "control", fake_control)

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/pipeline/cancel/run-123",
            headers=_auth_headers(),
        )
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    fake_control.revoke.assert_called_once()
