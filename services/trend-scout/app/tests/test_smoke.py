"""Smoke tests for the Trend Scout microservice scaffold (Phase 1).

Verifies:
- App factory creates the FastAPI app
- /health/live returns 200 with the expected payload
- /health/ping returns 200
- /api/v1/openapi.json is served
- Settings load with the TREND_SCOUT_ env prefix
- Database module imports and the check_db_connected helper is callable
- Celery app has the trend_scout queue with low priority
- Security module exports the expected scopes
- Alembic env.py imports the models
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TREND_SCOUT_SERVICE_ENV", "testing")
    monkeypatch.setenv("TREND_SCOUT_INTERNAL_API_TOKEN", "test-token-do-not-use")
    monkeypatch.setenv("TREND_SCOUT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("TREND_SCOUT_REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("TREND_SCOUT_CELERY_BROKER_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("TREND_SCOUT_CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    monkeypatch.setenv("TREND_SCOUT_AUDIT_LOG_ENABLED", "false")


def test_app_factory_creates_app() -> None:
    from app.main import create_app

    app = create_app()
    assert app.title == "dfp-trend-scout"
    assert app.version == "0.1.0"


def test_health_live_returns_200() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "dfp-trend-scout"
    assert body["version"] == "0.1.0"


def test_health_ping_returns_200() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_json_is_served() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "dfp-trend-scout"
    assert "/health/live" in body["paths"]


def test_settings_load_with_trend_scout_prefix() -> None:
    from app.config import Settings

    settings = Settings()
    assert settings.service_name == "dfp-trend-scout"
    assert settings.api_port == 8093
    assert settings.celery_queue == "trend_scout"
    assert settings.celery_task_priority == 1
    assert settings.celery_default_priority == 5
    assert settings.celery_max_priority == 10
    assert settings.audit_log_enabled is False


def test_database_module_imports() -> None:
    from app import database
    from app.database import Base, async_session_factory, check_db_connected, engine

    assert database is not None
    assert Base is not None
    assert async_session_factory is not None
    assert engine is not None
    assert callable(check_db_connected)


def test_celery_app_has_low_priority_queue() -> None:
    from app.celery_app import celery

    queues = celery.conf.task_queues
    assert queues is not None
    queue_names = {q.name for q in queues}
    assert "trend_scout" in queue_names
    queue = next(q for q in queues if q.name == "trend_scout")
    assert queue.queue_arguments.get("x-max-priority") == 10

    routes = celery.conf.task_routes
    assert routes is not None
    for pattern, route in routes.items():
        assert route["queue"] == "trend_scout"
        assert route["priority"] == 1

    assert celery.conf.task_queue_max_priority == 10
    assert celery.conf.task_default_priority == 5


def test_security_module_exports_scopes() -> None:
    from app.security import (
        ALL_SCOPES,
        SCOPE_ADMIN,
        SCOPE_READ,
        SCOPE_WRITE,
        has_scopes,
        require_scopes,
        verify_internal_token,
    )

    assert SCOPE_READ in ALL_SCOPES
    assert SCOPE_WRITE in ALL_SCOPES
    assert SCOPE_ADMIN in ALL_SCOPES
    assert callable(verify_internal_token)
    assert callable(require_scopes)
    assert callable(has_scopes)
    assert has_scopes({"trend_scout:read", "trend_scout:write"}, ["trend_scout:read"]) is True
    assert has_scopes({"trend_scout:read"}, ["trend_scout:write"]) is False


def test_alembic_env_imports_models() -> None:
    """Verify the alembic env.py exists, references the expected models, and the
    models register on Base.metadata. We do not exec the env module directly
    because alembic's __init__ clashes with the package layout; alembic itself
    runs env.py through its own CLI in real usage, and the imports below
    prove the configuration is wired correctly.
    """
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / "alembic" / "env.py"
    assert env_path.exists(), f"Alembic env.py not found at {env_path}"

    env_source = env_path.read_text()
    for required in (
        "from app.config import settings",
        "from app.database import Base",
        "from app.models import",
        "TrendSnapshot",
        "TrendReport",
        "TrendOpportunityScore",
        "SourceHealthRecord",
        "TrendWeight",
        "target_metadata=Base.metadata",
        "asyncio.run(run_async_migrations())",
    ):
        assert required in env_source, f"env.py missing required line: {required!r}"

    from app.models import (
        SourceHealthRecord,
        TrendOpportunityScore,
        TrendReport,
        TrendSnapshot,
        TrendWeight,
    )

    table_names = {
        TrendSnapshot.__tablename__,
        TrendReport.__tablename__,
        TrendOpportunityScore.__tablename__,
        SourceHealthRecord.__tablename__,
        TrendWeight.__tablename__,
    }
    assert table_names.issubset(set(TrendSnapshot.metadata.tables.keys()))


def test_health_ready_returns_expected_schema() -> None:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    for key in ("status", "service", "database", "redis", "celery", "openai_configured"):
        assert key in body
