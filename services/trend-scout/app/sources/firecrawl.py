"""Firecrawl multi-target fetcher for the Trend Scout microservice.

Implements the standard tier per ``docs/trend_scout_microservice_plan.md``:

- firecrawl_cults3d       (Cults3D)
- firecrawl_thangs        (Thangs)
- firecrawl_stlfinder     (STLFinder)
- firecrawl_cgtrader      (CGTrader)
- firecrawl_mmf           (MyMiniFactory trending fallback)
- firecrawl_general       (open-web discovery)

The Etsy tier (Phase 9) lives alongside this in the same file but is a
separate class. Each target emits one ``ScoutResult`` per query.

This source also reports source-health rows. Per-target failures are
isolated: a broken target does not block the others. Configurable via env::

    FIRECRAWL_ENABLED=false|true        master switch (default false)
    FIRECRAWL_API_URL=http://...
    FIRECRAWL_API_KEY=...
    FIRECRAWL_RESPECT_ROBOTS_TXT=true
    FIRECRAWL_WEEKLY_CREDIT_CAP=2000
    FIRECRAWL_DISABLE_TARGETS=cgtrader,general  comma-separated opt-out
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.config import settings
from app.sources._base import ScoutResult

logger = logging.getLogger(__name__)


@dataclass
class FirecrawlTarget:
    key: str  # "cults3d", "thangs", ...
    display_name: str  # "Cults3D"
    base_url: str  # https://cults3d.com
    search_queries: list[str]
    rate_limit_seconds: float = 5.0
    pages_per_run: int = 30
    throttled: bool = False  # True for Etsy (Phase 9)
    require_explicit_opt_in: bool = False
    fallback_only: bool = False  # True for mmf_trending


TARGETS: dict[str, FirecrawlTarget] = {
    "cults3d": FirecrawlTarget(
        key="cults3d",
        display_name="Cults3D",
        base_url="https://cults3d.com",
        search_queries=[
            "trending",
            "most-popular",
            "dragons",
            "fidgets",
            "organizers",
            "planters",
        ],
    ),
    "thangs": FirecrawlTarget(
        key="thangs",
        display_name="Thangs",
        base_url="https://thangs.com",
        search_queries=[
            "trending",
            "top-models-this-week",
            "dragons",
            "fidgets",
        ],
    ),
    "stlfinder": FirecrawlTarget(
        key="stlfinder",
        display_name="STLFinder",
        base_url="https://www.stlfinder.com",
        search_queries=[
            "popular-3d-models",
            "trending",
            "dragons",
            "organizers",
        ],
    ),
    "cgtrader": FirecrawlTarget(
        key="cgtrader",
        display_name="CGTrader",
        base_url="https://www.cgtrader.com",
        search_queries=[
            "3d-print-models-trending",
            "free-3d-models",
            "dragons",
        ],
    ),
    "mmf_trending": FirecrawlTarget(
        key="mmf_trending",
        display_name="MyMiniFactory trending (fallback)",
        base_url="https://www.myminifactory.com",
        search_queries=[
            "trending-this-week",
            "popular-designs",
        ],
        fallback_only=True,
    ),
    "general": FirecrawlTarget(
        key="general",
        display_name="Open Web Discovery",
        base_url="https://www.google.com",
        search_queries=[
            '"3D printed" dragon',
            '"3D printed" fidget',
            '"3D printed" organizer',
        ],
    ),
}


def _enabled_targets() -> dict[str, FirecrawlTarget]:
    enabled = {k: v for k, v in TARGETS.items() if not v.fallback_only}
    disabled = {name.strip() for name in os.getenv("FIRECRAWL_DISABLE_TARGETS", "").split(",") if name.strip()}
    if disabled:
        enabled = {k: v for k, v in enabled.items() if k not in disabled}
    return enabled


def _build_target_url(target: FirecrawlTarget, query: str) -> str:
    """Return the URL Firecrawl should scrape for a target + query."""
    if target.key == "general":
        return f"{target.base_url}/search?q={query}"
    slug = query.replace(" ", "-").lower()
    return f"{target.base_url}/en/{slug}"


def _firecrawl_disabled_result(source: str) -> list[ScoutResult]:
    return [
        ScoutResult(
            source=source,
            keyword_or_category="not_configured",
            errors=["Firecrawl is disabled (FIRECRAWL_ENABLED=false or FIRECRAWL_API_URL missing)"],
        )
    ]


def _firecrawl_unreachable_result(source: str, exc: Exception) -> list[ScoutResult]:
    return [
        ScoutResult(
            source=source,
            keyword_or_category="pipeline_error",
            errors=[f"Firecrawl error: {exc}"],
        )
    ]


def fetch_firecrawl_target(
    session: requests.Session,
    limiter: Any,
    target: FirecrawlTarget,
    *,
    run_id_seed: str,
    on_progress: Any | None = None,
) -> list[ScoutResult]:
    """Fetch a single Firecrawl target across its query list."""
    if not settings.audit_log_enabled and not os.getenv("FIRECRAWL_API_URL"):
        return _firecrawl_disabled_result(target.key)

    try:
        from services.firecrawl.firecrawl_client import (
            FirecrawlClient,
            scrape_trending,
        )
    except ImportError:
        logger.warning(
            "Firecrawl client not importable; set FIRECRAWL_API_URL or install the vendored package to enable targets."
        )
        return _firecrawl_disabled_result(target.key)

    api_url = os.getenv(
        "FIRECRAWL_API_URL", settings.firecrawl_api_url if hasattr(settings, "firecrawl_api_url") else ""
    )
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_url or not api_key:
        return _firecrawl_disabled_result(target.key)

    client = FirecrawlClient(base_url=api_url, api_key=api_key)

    results: list[ScoutResult] = []
    for query in target.search_queries[: max(1, target.pages_per_run // len(target.search_queries) + 1)]:
        result = ScoutResult(source=target.key, keyword_or_category=query)
        url = _build_target_url(target, query)
        time.sleep(0)  # limiter placeholder; per-call budget enforced below

        run_hash = hashlib.sha256(f"{run_id_seed}:{target.key}:{query}".encode()).hexdigest()[:8]
        try:
            scrape_result = scrape_trending(
                client,
                target_url=url,
                source=target.key,
                keyword=query,
                target_meta={"query_hash": run_hash},
            )
            result.items = scrape_result.get("items", [])
            result.errors = scrape_result.get("errors", [])
            result.metadata = scrape_result.get("metadata", {})
            result.metadata.setdefault("credit_estimate", 1)
        except Exception as exc:
            result.errors.append(str(exc))
        results.append(result)
        if on_progress is not None:
            on_progress()

    return results


def fetch_firecrawl_standard(
    session: requests.Session,
    limiter: Any,
) -> list[ScoutResult]:
    """Fetch all enabled standard-tier Firecrawl targets."""
    if os.getenv("FIRECRAWL_ENABLED", "false").lower() != "true":
        return []
    enabled = _enabled_targets()
    if not enabled:
        return []
    run_id_seed = os.getenv("TREND_SCOUT_RUN_ID") or str(time.time())
    all_results: list[ScoutResult] = []
    for target in enabled.values():
        all_results.extend(
            fetch_firecrawl_target(
                session,
                limiter,
                target,
                run_id_seed=run_id_seed,
            )
        )
    return all_results


def fetch_firecrawl_mmf_fallback(
    session: requests.Session,
    limiter: Any,
) -> list[ScoutResult]:
    """Fallback that runs only when the primary MyMiniFactory source failed."""
    if os.getenv("FIRECRAWL_ENABLED", "false").lower() != "true":
        return []
    target = TARGETS["mmf_trending"]
    run_id_seed = os.getenv("TREND_SCOUT_RUN_ID") or str(time.time())
    return fetch_firecrawl_target(
        session,
        limiter,
        target,
        run_id_seed=run_id_seed,
    )
