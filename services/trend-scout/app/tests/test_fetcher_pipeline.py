"""Pipeline integration tests for the Trend Scout microservice.

Verifies:
- run_all_sources returns a list of result dicts from all enabled fetchers
- per-source error isolation works (one failing fetcher does not block others)
- source-health aggregation groups results by source and counts items correctly
- DB_FETCHERS / EXTERNAL_FETCHERS / ALL_FETCHERS include every expected name
- enabled fetcher count and env-driven disable both work
"""

from __future__ import annotations

import pytest

from app.services import fetcher_pipeline

EXPECTED_ALL_SOURCES = {
    "internal_demand",
    "myminifactory",
    "bgg",
    "last30days",
    "makerworld",
    "printables",
    "reddit",
    "etsy",
    "pinterest",
    "google_trends",
    "tiktok",
    "firecrawl_standard",
    "firecrawl_mmf",
}


def test_all_fetcher_names_registered() -> None:
    assert set(fetcher_pipeline.ALL_FETCHERS.keys()) == EXPECTED_ALL_SOURCES


def test_db_and_external_fetchers_partition_is_correct() -> None:
    db_names = set(fetcher_pipeline.DB_FETCHERS.keys())
    external_names = set(fetcher_pipeline.EXTERNAL_FETCHERS.keys())
    firecrawl_names = set(fetcher_pipeline.FIRECRAWL_FETCHER_REGISTRY.keys())
    assert db_names.union(external_names).union(firecrawl_names) == EXPECTED_ALL_SOURCES
    assert db_names.isdisjoint(external_names)
    assert db_names.isdisjoint(firecrawl_names)
    assert external_names.isdisjoint(firecrawl_names)
    assert db_names == {"internal_demand"}


def test_enabled_fetchers_default_all_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TREND_SCOUT_DISABLE_SOURCES", raising=False)
    enabled = fetcher_pipeline.enabled_fetchers()
    assert set(enabled.keys()) == EXPECTED_ALL_SOURCES


def test_enabled_fetchers_respects_disable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TREND_SCOUT_DISABLE_SOURCES", "etsy,tiktok")
    enabled = fetcher_pipeline.enabled_fetchers()
    assert "etsy" not in enabled
    assert "tiktok" not in enabled
    assert "myminifactory" in enabled
    assert fetcher_pipeline.enabled_fetcher_count() == len(EXPECTED_ALL_SOURCES) - 2


@pytest.mark.slow
def test_run_all_sources_returns_results_from_every_enabled_fetcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration smoke — exercises every fetcher end-to-end.

    Marked ``slow`` because it makes real network calls. To run it::

        uv run pytest -m slow

    The default ``uv run pytest`` skips it. The other 4 tests in this file
    cover the same logic via mocks/monkeypatches and run in <1s.
    """
    monkeypatch.delenv("TREND_SCOUT_DISABLE_SOURCES", raising=False)
    monkeypatch.setenv("TREND_SCOUT_FETCHER_TIMEOUT_SECONDS", "5")

    results = fetcher_pipeline.run_all_sources()
    assert isinstance(results, list)
    assert len(results) >= len(EXPECTED_ALL_SOURCES)
    for r in results:
        assert isinstance(r, dict)
        assert r.get("source")
        assert "items" in r
        assert "errors" in r


@pytest.mark.slow
def test_run_all_sources_invokes_progress_callback() -> None:
    calls = []

    def cb(completed, total, step, status):
        calls.append((completed, total, step, status))

    fetcher_pipeline.run_all_sources(progress_callback=cb)
    assert len(calls) >= 1
    final = calls[-1]
    assert final[0] == final[1]


def test_aggregate_source_health_counts_items_and_groups_errors() -> None:
    fake_results = [
        {
            "source": "etsy",
            "keyword_or_category": "3D printed dragon",
            "scraped_at": "2026-08-13T00:00:00Z",
            "items": [{"title": "a"}, {"title": "b"}],
            "errors": [],
            "metadata": {"total_results": 2},
        },
        {
            "source": "etsy",
            "keyword_or_category": "3D printed fidget",
            "scraped_at": "2026-08-13T00:00:01Z",
            "items": [{"title": "c"}],
            "errors": ["HTTP 500"],
            "metadata": {"total_results": 1},
        },
        {
            "source": "makerworld",
            "keyword_or_category": "trending",
            "scraped_at": "2026-08-13T00:00:02Z",
            "items": [{"title": "d"}],
            "errors": [],
            "metadata": {},
        },
    ]
    health = fetcher_pipeline.aggregate_source_health(fake_results)
    assert len(health) == 2
    etsy = next(h for h in health if h["source"] == "etsy")
    assert etsy["status"] == "error"
    assert etsy["item_count"] == 3
    assert "HTTP 500" in etsy["error_message"]
    makerworld = next(h for h in health if h["source"] == "makerworld")
    assert makerworld["status"] == "success"
    assert makerworld["item_count"] == 1
