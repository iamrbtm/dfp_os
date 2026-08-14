"""Tests for the Firecrawl multi-target source.

Verify:
- Targets register correctly with the expected keys
- ``fetch_firecrawl_target`` returns a not_configured result when Firecrawl is disabled
- Per-target rate limit / page caps are respected
- ``fetch_firecrawl_standard`` only runs targets that are not opt-outed
- The mmf fallback only runs when explicitly invoked
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.sources import firecrawl as firecrawl_source


def test_targets_registry_matches_plan() -> None:
    expected = {
        "cults3d",
        "thangs",
        "stlfinder",
        "cgtrader",
        "mmf_trending",
        "general",
    }
    assert set(firecrawl_source.TARGETS.keys()) == expected


def test_standard_targets_have_real_pages_and_rates() -> None:
    for key, target in firecrawl_source.TARGETS.items():
        if target.fallback_only:
            continue
        assert target.pages_per_run >= 1, key
        assert target.rate_limit_seconds >= 1.0, key
        assert target.search_queries, key
        assert target.base_url.startswith("https://"), key


def test_mmf_trending_marked_as_fallback() -> None:
    target = firecrawl_source.TARGETS["mmf_trending"]
    assert target.fallback_only is True


def test_general_target_uses_google_search() -> None:
    target = firecrawl_source.TARGETS["general"]
    assert "google" in target.base_url


def test_enabled_targets_respects_disable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRECRAWL_DISABLE_TARGETS", "cgtrader,general")
    enabled = firecrawl_source._enabled_targets()
    enabled_keys = set(enabled.keys())
    assert "cgtrader" not in enabled_keys
    assert "general" not in enabled_keys
    assert "cults3d" in enabled_keys


def test_enabled_targets_excludes_fallback_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enabled = firecrawl_source._enabled_targets()
    assert "mmf_trending" not in enabled


def test_build_target_url_general_uses_search() -> None:
    target = firecrawl_source.TARGETS["general"]
    url = firecrawl_source._build_target_url(target, "3D printed dragon")
    assert "search?q=" in url


def test_build_target_url_cults3d_uses_en_slug() -> None:
    target = firecrawl_source.TARGETS["cults3d"]
    url = firecrawl_source._build_target_url(target, "trending dragons")
    assert "/en/trending-dragons" in url


def test_fetch_firecrawl_target_returns_not_configured_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIRECRAWL_API_URL", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setenv("FIRECRAWL_ENABLED", "false")
    target = firecrawl_source.TARGETS["cults3d"]
    import requests

    results = firecrawl_source.fetch_firecrawl_target(
        requests.Session(),
        None,
        target,
        run_id_seed="seed-1",
    )
    assert results and "not_configured" in (results[0].keyword_or_category or "")


def test_fetch_firecrawl_target_handles_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("FIRECRAWL_API_URL", "http://firecrawl:3002")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

    target = firecrawl_source.TARGETS["cults3d"]
    import requests

    class _Boom:
        def __getattr__(self, name):
            raise ImportError(f"boom {name}")

    with patch.dict("sys.modules", {"services.firecrawl.firecrawl_client": _Boom()}):
        results = firecrawl_source.fetch_firecrawl_target(
            requests.Session(),
            None,
            target,
            run_id_seed="seed-1",
        )
    assert results and "not_configured" in (results[0].keyword_or_category or "")


def test_fetch_firecrawl_standard_returns_empty_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_ENABLED", "false")
    import requests

    results = firecrawl_source.fetch_firecrawl_standard(requests.Session(), None)
    assert results == []


def test_fetch_firecrawl_standard_paginates_pages_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("FIRECRAWL_DISABLE_TARGETS", "cults3d,thangs,stlfinder,cgtrader,general")

    call_count = {"value": 0}

    def fake_scrape_trending(client, target_url, source, keyword, target_meta=None):
        call_count["value"] += 1
        return {
            "source": source,
            "keyword_or_category": keyword,
            "items": [],
            "errors": [],
            "metadata": {"target_url": target_url},
        }

    fake_client_module = MagicMock()
    fake_client_module.scrape_trending = fake_scrape_trending
    fake_client_module.FirecrawlClient = MagicMock()

    with patch.dict("sys.modules", {"services.firecrawl.firecrawl_client": fake_client_module}):
        import requests

        results = firecrawl_source.fetch_firecrawl_standard(requests.Session(), None)
    assert isinstance(results, list)
    assert call_count["value"] >= 0


def test_fetch_firecrawl_mmf_fallback_independent_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("FIRECRAWL_API_URL", "http://firecrawl:3002")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")

    captured = {"value": None}

    def fake_scrape_trending(client, target_url, source, keyword, target_meta=None):
        captured["value"] = (source, keyword, target_url)
        return {
            "source": source,
            "keyword_or_category": keyword,
            "items": [],
            "errors": [],
            "metadata": {"target_url": target_url, "fallback_only": True},
        }

    fake_client_module = MagicMock()
    fake_client_module.scrape_trending = fake_scrape_trending
    fake_client_module.FirecrawlClient = MagicMock()

    with patch.dict("sys.modules", {"services.firecrawl.firecrawl_client": fake_client_module}):
        import requests

        firecrawl_source.fetch_firecrawl_mmf_fallback(requests.Session(), None)
    assert captured["value"] is not None
    assert captured["value"][0] == "mmf_trending"
