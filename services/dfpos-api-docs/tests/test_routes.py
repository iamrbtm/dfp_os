from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_spec_cache():
    import app.routes
    app.routes._spec_cache["data"] = None
    app.routes._spec_cache["fetched_at"] = 0
    app.routes._spec_cache["source"] = None


@pytest.fixture
def spec_file(tmp_path):
    return tmp_path / "openapi.json"


@pytest.fixture
def app(spec_file, monkeypatch):
    from app import create_app
    monkeypatch.setenv("FLASK_ENV", "development")
    app = create_app()
    app.config.update({
        "TESTING": True,
        "DFPOS_OPENAPI_URL": "",
        "DFPOS_OPENAPI_FALLBACK_PATH": str(spec_file),
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _write_spec(app, spec_data):
    path = Path(app.config["DFPOS_OPENAPI_FALLBACK_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec_data))
    return path


def test_health_no_spec(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "degraded"
    assert data["spec_loaded"] is False


def test_health_with_local_spec(app, client):
    _write_spec(app, {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {"/test": {"get": {"responses": {"200": {"description": "OK"}}}}},
    })
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["spec_loaded"] is True


def test_index_no_spec(client):
    resp = client.get("/")
    assert resp.status_code == 503


def test_index_with_spec(app, client):
    _write_spec(app, {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    })
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Redoc" in resp.data or b"redoc" in resp.data


def test_openapi_json_no_spec(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 503


def test_openapi_json_with_spec(app, client):
    _write_spec(app, {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    })
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["info"]["title"] == "Test API"


def test_api_proxy_route(client):
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code in (200, 503)


def test_404(client):
    resp = client.get("/nonexistent")
    assert resp.status_code == 404


def test_validate_cli():
    from app.cli import _validate_openapi

    errors = _validate_openapi({})
    assert any("openapi" in m.lower() for _, m in errors)
    assert any("info" in m.lower() for _, m in errors)

    errors = _validate_openapi({
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {"/x": {"get": {"responses": {"200": {"description": "OK"}}}}},
    })
    assert len(errors) == 0

    errors = _validate_openapi({
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {"/x": {"get": {}}},
    })
    assert any("responses" in m.lower() for _, m in errors)


def test_docs_auth_required_rejects_missing_credentials(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "DOCS_AUTH_REQUIRED", True)
    monkeypatch.setattr(Config, "DOCS_USERNAME", "")
    monkeypatch.setattr(Config, "DOCS_PASSWORD", "")

    with pytest.raises(RuntimeError, match="Docs auth is required"):
        Config.validate()
