"""Per-source unit tests for the migrated Trend Scout fetcher.

Each test verifies that a fetcher returns a ScoutResult with a sensible
default shape when network/API/credentials are unavailable, without crashing
the pipeline. Most fetchers assume a real ``requests.Session``; we provide one
with a tight timeout so the network calls fail fast and the fetcher's error
path is exercised.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from app.sources._base import RateLimiter, ScoutResult


@pytest.fixture
def short_timeout_session() -> requests.Session:
    """A requests.Session with a 2-second timeout so unsucessful network calls
    fail fast and the fetcher's error path is exercised."""
    s = requests.Session()

    def _patch(method: Any) -> Any:
        original = method

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("timeout", 2.0)
            return original(*args, **kwargs)

        return wrapper

    s.get = _patch(s.get)  # type: ignore[method-assign]
    s.post = _patch(s.post)  # type: ignore[method-assign]
    return s


def _call_fetcher(name: str, fn: Any, session: Any = None) -> list[ScoutResult]:
    """Run a fetcher with the orchestrator's contract ``(session, limiter)``."""
    results = fn(session, RateLimiter(interval=0))
    assert isinstance(results, list)
    assert len(results) >= 1
    for r in results:
        assert isinstance(r, ScoutResult)
        assert r.source == name or r.source in (name, f"{name}_error", "pipeline_error", "not_configured")
    return results


def test_base_scout_result_to_dict_round_trip() -> None:
    r = ScoutResult(source="test", keyword_or_category="kw")
    r.items.append({"title": "abc"})
    r.metadata["x"] = 1
    payload = r.to_dict()
    assert payload["source"] == "test"
    assert payload["keyword_or_category"] == "kw"
    assert payload["items"] == [{"title": "abc"}]
    assert payload["metadata"]["x"] == 1
    # The dataclass auto-fills metadata with derived fields.
    assert "has_signal" in payload["metadata"]
    assert "item_count" in payload["metadata"]


def test_internal_demand_returns_structured_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TREND_SCOUT_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("TREND_SCOUT_FLASK_INTERNAL_TOKEN", raising=False)
    monkeypatch.setenv("TREND_SCOUT_FLASK_BASE_URL", "http://127.0.0.1:1")
    from app.sources.internal_demand import fetch_internal_demand

    results = _call_fetcher("internal_demand", fetch_internal_demand, None)
    assert results[0].errors or results[0].metadata.get("note")
    assert results[0].keyword_or_category in (
        "not_configured",
        "buyer_intent",
        "pipeline_error",
    )


def test_internal_demand_uses_shared_internal_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import internal_demand

    captured: dict[str, object] = {}

    def fake_fetch(**kwargs: object) -> list[ScoutResult]:
        captured.update(kwargs)
        return [ScoutResult(source="internal_demand", keyword_or_category="buyer_intent")]

    monkeypatch.setenv("TREND_SCOUT_INTERNAL_API_TOKEN", "shared-token")
    monkeypatch.delenv("TREND_SCOUT_FLASK_INTERNAL_TOKEN", raising=False)
    monkeypatch.setattr(internal_demand, "_fetch_internal_demand_sync", fake_fetch)

    results = internal_demand.fetch_internal_demand()

    assert results[0].source == "internal_demand"
    assert captured["token"] == "shared-token"


def test_bgg_returns_list_or_graceful_error(short_timeout_session: requests.Session) -> None:
    from app.sources.bgg import fetch_hot_items

    results = _call_fetcher("bgg", fetch_hot_items, short_timeout_session)
    assert results[0].source == "bgg"


def test_makerworld_handles_missing_curl_cffi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makerworld relies on curl_cffi; verify it returns a structured error
    rather than crashing when the import fails."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("curl_cffi"):
            raise ImportError("simulated missing curl_cffi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from app.sources.makerworld import fetch_trending

    results = _call_fetcher("makerworld", fetch_trending)
    assert isinstance(results[0], ScoutResult)
    assert results[0].source == "makerworld"


def test_myminifactory_returns_structured_result(short_timeout_session: requests.Session) -> None:
    from app.sources.myminifactory import fetch_trending

    results = _call_fetcher("myminifactory", fetch_trending, short_timeout_session)
    assert results[0].source == "myminifactory"


def test_printables_returns_structured_result(short_timeout_session: requests.Session) -> None:
    from app.sources.printables import fetch_trending

    results = _call_fetcher("printables", fetch_trending, short_timeout_session)
    assert results[0].source == "printables"


def test_reddit_returns_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """reddit uses a module-level REDDIT_REQUEST_INTERVAL sleep; shrink both
    SUBREDDITS and FEED_TYPES to make this fast."""
    from app.sources import reddit

    monkeypatch.setattr(reddit, "REDDIT_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr(reddit, "SUBREDDITS", reddit.SUBREDDITS[:1])
    monkeypatch.setattr(reddit, "FEED_TYPES", reddit.FEED_TYPES[:1])
    from app.sources.reddit import fetch_trending

    results = _call_fetcher("reddit", fetch_trending)
    assert results[0].source == "reddit"


def test_etsy_returns_error_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ETSY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.sources.etsy import fetch_trending

    results = _call_fetcher("etsy", fetch_trending)
    assert results[0].source == "etsy"
    assert "ETSY_API_KEY" in "; ".join(results[0].errors) or "not_configured" in results[0].keyword_or_category


def test_pinterest_returns_error_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PINTEREST_API_KEY", raising=False)
    from app.sources.pinterest import fetch_trending

    results = _call_fetcher("pinterest", fetch_trending)
    assert results[0].source == "pinterest"
    assert results[0].errors or results[0].metadata.get("note")


def test_tiktok_returns_error_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIKTOK_RESEARCH_ACCESS_TOKEN", raising=False)
    from app.sources.tiktok import fetch_trending

    results = _call_fetcher("tiktok", fetch_trending)
    assert results[0].source == "tiktok"
    assert results[0].errors or results[0].metadata.get("note")


def test_google_trends_returns_structured_result(short_timeout_session: requests.Session) -> None:
    from app.sources.google_trends import fetch_trending

    results = _call_fetcher("google_trends", fetch_trending, short_timeout_session)
    assert results[0].source == "google_trends"


def test_last30days_returns_structured_result(short_timeout_session: requests.Session) -> None:
    from app.sources.last30days import fetch_trending

    results = _call_fetcher("last30days", fetch_trending, short_timeout_session)
    assert results[0].source == "last30days"


def test_last30days_empty_env_uses_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import last30days

    monkeypatch.setenv("LAST30DAYS_RAW_FILE", "")

    results = last30days.fetch_trending()

    assert results[0].source == "last30days"
    assert last30days.DEFAULT_RAW_FILE in "; ".join(results[0].errors)
