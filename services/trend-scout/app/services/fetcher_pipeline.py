"""Fetcher orchestration for the Trend Scout microservice.

Concurrently runs all configured source fetchers, isolates per-source
failures, and returns a flat list of result dicts. The DB persistence and
analysis steps live in app.services.analysis (Phase 3) and the Celery
tasks in app.workers.tasks (Phase 4).
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import requests

from app.config import settings
from app.sources import (
    RateLimiter,
    ScoutResult,
    fetch_bgg,
    fetch_etsy,
    fetch_google_trends,
    fetch_internal_demand,
    fetch_last30days,
    fetch_makerworld,
    fetch_myminifactory,
    fetch_pinterest,
    fetch_printables,
    fetch_reddit,
    fetch_tiktok,
)
from app.sources.firecrawl import (
    fetch_firecrawl_mmf_fallback,
    fetch_firecrawl_standard,
)

logger = logging.getLogger(__name__)


DB_FETCHERS: dict[str, Callable[..., list[ScoutResult]]] = {
    "internal_demand": fetch_internal_demand,
}

EXTERNAL_FETCHERS: dict[str, Callable[..., list[ScoutResult]]] = {
    "myminifactory": fetch_myminifactory,
    "bgg": fetch_bgg,
    "last30days": fetch_last30days,
    "makerworld": fetch_makerworld,
    "printables": fetch_printables,
    "reddit": fetch_reddit,
    "etsy": fetch_etsy,
    "pinterest": fetch_pinterest,
    "google_trends": fetch_google_trends,
    "tiktok": fetch_tiktok,
}

# Firecrawl targets get registered as a single fetcher under the umbrella
# key `firecrawl_standard` so the existing pipeline runner picks them up.
# The fetcher fans out to per-target sources internally. mmf_trending stays
# as its own key because the orchestrator invokes it as a fallback only.
FIRECRAWL_FETCHER_REGISTRY = {
    "firecrawl_standard": lambda session, limiter: fetch_firecrawl_standard(session, limiter),
    "firecrawl_mmf": lambda session, limiter: fetch_firecrawl_mmf_fallback(session, limiter),
}

ALL_FETCHERS: dict[str, Callable[..., list[ScoutResult]]] = {
    **DB_FETCHERS,
    **EXTERNAL_FETCHERS,
    **FIRECRAWL_FETCHER_REGISTRY,
}


def _load_source_enabled_state() -> dict[str, bool]:
    """Read per-source enable/disable state from env (Phase 3 replaces with weights table).

    Until weights land in the microservice DB the default is "all enabled" so
    the migration is faithful to the prior behavior. Source toggles can be
    applied via env (``TREND_SCOUT_DISABLE_SOURCES=etsy,tiktok``).
    """
    disabled = {name.strip() for name in os.getenv("TREND_SCOUT_DISABLE_SOURCES", "").split(",") if name.strip()}
    return {name: name not in disabled for name in ALL_FETCHERS}


def enabled_fetchers() -> dict[str, Callable[..., list[ScoutResult]]]:
    state = _load_source_enabled_state()
    return {name: fn for name, fn in ALL_FETCHERS.items() if state.get(name, True)}


def enabled_fetcher_count() -> int:
    return len(enabled_fetchers())


def _run_fetcher(name: str, fetcher: Callable[..., list[ScoutResult]]) -> list[ScoutResult]:
    """Execute a fetcher inside its own requests.Session with error isolation."""
    limiter = RateLimiter()
    try:
        with requests.Session() as session:
            logger.info("[%s] Fetcher starting...", name)
            result = fetcher(session, limiter)
            logger.info("[%s] Fetcher completed: %d results", name, len(result))
            return result
    except Exception as exc:
        logger.warning("[%s] Fetcher FAILED: %s", name, exc)
        return [
            ScoutResult(
                source=name,
                keyword_or_category="pipeline_error",
                errors=[str(exc)],
            )
        ]


def _source_health_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_map: dict[str, dict[str, Any]] = {}
    for r in results:
        source = r.get("source", "unknown")
        if source not in source_map:
            source_map[source] = {
                "source": source,
                "status": "success",
                "keyword": None,
                "item_count": 0,
                "error_message": None,
                "scraped_at": r.get("scraped_at"),
                "metadata": r.get("metadata", {}),
            }
        errors = r.get("errors", [])
        if errors:
            source_map[source]["status"] = "error"
            source_map[source]["error_message"] = "; ".join(errors)
        items = r.get("items", [])
        source_map[source]["item_count"] += len(items)
        kw = r.get("keyword_or_category")
        if kw and kw not in ("pipeline_error", "not_configured", "configured", "analysis", ""):
            source_map[source]["keyword"] = kw
    return list(source_map.values())


def run_all_sources(progress_callback: Callable | None = None) -> list[dict[str, Any]]:
    """Run all enabled fetchers concurrently and return result dicts.

    The async fetchers (internal_demand) live in DB_FETCHERS and run
    sequentially on the calling thread because the ThreadPoolExecutor cannot
    await coroutines. External fetchers run concurrently in a thread pool.

    ``progress_callback(completed, total, step_name, status)`` is called as
    each fetcher finishes, matching the contract the Celery task uses.
    """
    all_results: list[ScoutResult] = []
    fetchers = enabled_fetchers()
    db_fetchers = {n: f for n, f in fetchers.items() if n in DB_FETCHERS}
    external_fetchers = {n: f for n, f in fetchers.items() if n in EXTERNAL_FETCHERS}
    total_sources = len(db_fetchers) + len(external_fetchers)
    pipeline_total = total_sources + 1
    completed = 0

    for name, fetcher in db_fetchers.items():
        completed += 1
        try:
            logger.info("[%s] DB fetcher starting...", name)
            batch = fetcher(None, RateLimiter(interval=0))
            all_results.extend(batch)
            logger.info("[%s] DB fetcher completed: %d results", name, len(batch))
            if progress_callback:
                progress_callback(completed, pipeline_total, name, "completed")
        except Exception as exc:
            logger.warning("[%s] DB fetcher FAILED: %s", name, exc)
            if progress_callback:
                progress_callback(completed, pipeline_total, name, "failed")
            all_results.append(
                ScoutResult(
                    source=name,
                    keyword_or_category="pipeline_error",
                    errors=[str(exc)],
                )
            )

    with ThreadPoolExecutor(max_workers=settings.fetcher_pool_workers) as executor:
        future_map = {executor.submit(_run_fetcher, name, fn): name for name, fn in external_fetchers.items()}
        for future in as_completed(future_map):
            name = future_map[future]
            completed += 1
            try:
                batch = future.result(timeout=settings.fetcher_timeout_seconds * 4)
                all_results.extend(batch)
                logger.info(
                    "[%s] Fetcher completed successfully (%d/%d)",
                    name,
                    completed,
                    total_sources,
                )
                if progress_callback:
                    progress_callback(completed, pipeline_total, name, "completed")
            except Exception as exc:
                logger.error(
                    "[%s] Fetcher timed out or crashed: %s (%d/%d)",
                    name,
                    exc,
                    completed,
                    total_sources,
                )
                if progress_callback:
                    progress_callback(completed, pipeline_total, name, "failed")
                all_results.append(
                    ScoutResult(
                        source=name,
                        keyword_or_category="pipeline_error",
                        errors=[f"Fetcher crashed: {exc}"],
                    )
                )

    return [r.to_dict() for r in all_results]


def aggregate_source_health(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Public wrapper around the internal aggregator for callers (Phase 3+)."""
    return _source_health_from_results(results)
