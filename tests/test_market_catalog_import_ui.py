from __future__ import annotations

import pytest

from app.services.market_catalog_importers.registry import (
    get_importer,
    list_importers,
    run_importer,
)


def test_registry_lists_tennesseefairs():
    importers = list_importers()
    assert any(i.key == "tennesseefairs" for i in importers)
    t = get_importer("tennesseefairs")
    assert t is not None
    assert "https://tennesseefairs.com/calendar/" in t.source_urls
    assert "https://tennesseefairs.com/directory/" in t.source_urls


def test_unknown_importer_key_raises():
    with pytest.raises(KeyError):
        run_importer("does-not-exist", dry_run=True)


@pytest.fixture()
def fake_summary():
    return {
        "calendar_count": 45,
        "directory_count": 59,
        "merged_count": 60,
        "created": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": True,
        "schema_valid": True,
        "schema_error": None,
        "preview": [{"name": "Clay County Fair", "city": "Celina", "state": "TN", "anchor_date": "2026-05-26", "has_contact": True}],
    }


def test_listings_page_shows_websites_tab(client, login_admin):
    resp = client.get("/market-catalog/")
    assert resp.status_code == 200
    assert b"Websites" in resp.data
    assert b"Tennessee Fairs" in resp.data


def test_run_import_dry_run_route(client, login_admin, monkeypatch, fake_summary):
    import app.blueprints.market_catalog.routes as routes

    monkeypatch.setattr(routes, "run_importer", lambda key, *, dry_run=True, actor=None: {**fake_summary, "dry_run": dry_run})
    resp = client.post("/market-catalog/imports/tennesseefairs/run", data={})
    assert resp.status_code == 200
    assert b"Dry run" in resp.data
    assert b"Clay County Fair" in resp.data


def test_run_import_commit_route(client, login_admin, monkeypatch, fake_summary):
    import app.blueprints.market_catalog.routes as routes

    captured = {}

    def _fake(key, *, dry_run=True, actor=None):
        captured["dry_run"] = dry_run
        return {**fake_summary, "dry_run": dry_run, "created": 3, "skipped": 0}

    monkeypatch.setattr(routes, "run_importer", _fake)
    resp = client.post(
        "/market-catalog/imports/tennesseefairs/run",
        data={"commit": "1", "csrf_token": "x"},
    )
    assert resp.status_code == 200
    assert captured["dry_run"] is False
    assert b"Committed to Market Catalog" in resp.data
    assert b"Created" in resp.data


def test_run_import_route_handles_error(client, login_admin, monkeypatch):
    import app.blueprints.market_catalog.routes as routes

    def _boom(key, *, dry_run=True, actor=None):
        raise RuntimeError("Firecrawl is down")

    monkeypatch.setattr(routes, "run_importer", _boom)
    resp = client.post("/market-catalog/imports/tennesseefairs/run", data={})
    assert resp.status_code == 200
    assert b"Import failed" in resp.data
    assert b"Firecrawl is down" in resp.data
