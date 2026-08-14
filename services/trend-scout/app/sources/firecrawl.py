"""Firecrawl multi-target fetcher for the Trend Scout microservice.

Implements both tiers per ``docs/trend_scout_microservice_plan.md``:

STANDARD tier (runs every cycle):

- firecrawl_cults3d       (Cults3D)
- firecrawl_thangs        (Thangs)
- firecrawl_stlfinder     (STLFinder)
- firecrawl_cgtrader      (CGTrader)
- firecrawl_mmf           (MyMiniFactory trending fallback)
- firecrawl_general       (open-web discovery)

THROTTLED tier (randomized with min-days gate, opt-in required):

- firecrawl_etsy          (Etsy)

Each target emits one ``ScoutResult`` per query. Configurable via env::

    FIRECRAWL_ENABLED=false|true                   master switch (default false)
    FIRECRAWL_API_URL=http://...
    FIRECRAWL_API_KEY=...
    FIRECRAWL_RESPECT_ROBOTS_TXT=true
    FIRECRAWL_WEEKLY_CREDIT_CAP=2000
    FIRECRAWL_DISABLE_TARGETS=cgtrader,general     comma-separated opt-out
    FIRECRAWL_ALLOW_ETSY=true                      opt-in for Etsy tier
    FIRECRAWL_ETSY_RUN_PROBABILITY=0.15            random draw threshold (default ~1-in-7)
    FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS=14        minimum gap between Etsy fetches
    FIRECRAWL_ETSY_MIN_INTERVAL_SECONDS=30        per-call rate limit
    FIRECRAWL_ETSY_MAX_PAGES_PER_RUN=20           hard cap on Etsy queries
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import settings
from app.sources._base import ScoutResult

logger = logging.getLogger(__name__)


@dataclass
class FirecrawlTarget:
    key: str
    display_name: str
    base_url: str
    search_queries: list[str]
    rate_limit_seconds: float = 5.0
    pages_per_run: int = 30
    throttled: bool = False
    require_explicit_opt_in: bool = False
    fallback_only: bool = False


ETSY_TARGET = FirecrawlTarget(
    key="etsy",
    display_name="Etsy (scraped, throttled)",
    base_url="https://www.etsy.com",
    search_queries=[
        "3D printed dragon",
        "3D printed fidget",
        "custom keychain",
        "3D printed earrings",
        "3D printed planter",
    ],
    rate_limit_seconds=30.0,
    pages_per_run=20,
    throttled=True,
    require_explicit_opt_in=True,
)


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


def _etsy_target() -> FirecrawlTarget:
    target = FirecrawlTarget(
        key=ETSY_TARGET.key,
        display_name=ETSY_TARGET.display_name,
        base_url=ETSY_TARGET.base_url,
        search_queries=list(ETSY_TARGET.search_queries),
        rate_limit_seconds=float(os.getenv("FIRECRAWL_ETSY_MIN_INTERVAL_SECONDS", "30")),
        pages_per_run=int(os.getenv("FIRECRAWL_ETSY_MAX_PAGES_PER_RUN", "20")),
        throttled=True,
        require_explicit_opt_in=True,
    )
    return target


def _enabled_targets() -> dict[str, FirecrawlTarget]:
    enabled = {k: v for k, v in TARGETS.items() if not v.fallback_only}
    disabled = {name.strip() for name in os.getenv("FIRECRAWL_DISABLE_TARGETS", "").split(",") if name.strip()}
    if disabled:
        enabled = {k: v for k, v in enabled.items() if k not in disabled}
    return enabled


def _etsy_allowed() -> bool:
    return os.getenv("FIRECRAWL_ALLOW_ETSY", "false").lower() == "true"


def _etsy_compliance_ok() -> bool:
    from app.compliance import gate_etsy_opt_in

    allowed, _ = gate_etsy_opt_in(_etsy_allowed())
    return allowed


def _etsy_should_run(run_id_seed: str) -> tuple[bool, str]:
    """Random draw + min-days gate."""
    if not _etsy_allowed():
        return False, "opt_in_disabled"
    if not _etsy_compliance_ok():
        return False, "compliance_missing"
    min_days = int(os.getenv("FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS", "14"))
    probability = float(os.getenv("FIRECRAWL_ETSY_RUN_PROBABILITY", "0.15"))

    last_run_iso = os.getenv("FIRECRAWL_ETSY_LAST_RUN_AT")
    if last_run_iso:
        try:
            last_run = datetime.fromisoformat(last_run_iso)
            days_since = (datetime.now(timezone.utc) - last_run).days
            if days_since < min_days:
                return False, f"min_days_not_met ({days_since}/{min_days})"
        except ValueError:
            pass

    digest = hashlib.sha256(f"{run_id_seed}:etsy".encode()).hexdigest()
    draw = int(digest[:8], 16) / 0xFFFFFFFF
    if draw > probability:
        return False, f"random_skip (draw={draw:.3f} > prob={probability})"
    return True, "selected"


def mark_etsy_ran() -> None:
    """Record the current time as Etsy's last run timestamp.

    Phase 9 stores this in-process (os.environ). Phase 10 backs it with Redis
    so it survives process restarts.
    """
    os.environ["FIRECRAWL_ETSY_LAST_RUN_AT"] = datetime.now(timezone.utc).isoformat()


def _build_target_url(target: FirecrawlTarget, query: str) -> str:
    if target.key == "general":
        return f"{target.base_url}/search?q={query}"
    if target.key == "etsy":
        return f"{target.base_url}/search?q={query.replace(' ', '+')}&sort=most_relevant"
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


def _firecrawl_throttled_result(source: str, reason: str) -> list[ScoutResult]:
    return [
        ScoutResult(
            source=source,
            keyword_or_category="throttled",
            errors=[],
            metadata={"throttled": True, "throttle_reason": reason, "items": []},
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
        "FIRECRAWL_API_URL",
        settings.firecrawl_api_url if hasattr(settings, "firecrawl_api_url") else "",
    )
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_url or not api_key:
        return _firecrawl_disabled_result(target.key)

    client = FirecrawlClient(base_url=api_url, api_key=api_key)

    results: list[ScoutResult] = []
    cap = max(1, target.pages_per_run // len(target.search_queries) + 1)
    for query in target.search_queries[:cap]:
        result = ScoutResult(source=target.key, keyword_or_category=query)
        url = _build_target_url(target, query)

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


def fetch_firecrawl_etsy(
    session: requests.Session,
    limiter: Any,
) -> list[ScoutResult]:
    """Etsy tier with random throttling + min-days gate + compliance gate."""
    run_id_seed = os.getenv("TREND_SCOUT_RUN_ID") or str(time.time())
    should_run, reason = _etsy_should_run(run_id_seed)
    if not should_run:
        return _firecrawl_throttled_result("etsy", reason)

    target = _etsy_target()
    results = fetch_firecrawl_target(
        session,
        limiter,
        target,
        run_id_seed=run_id_seed,
    )
    mark_etsy_ran()
    return results


def fetch_firecrawl_mmf_fallback(
    session: requests.Session,
    limiter: Any,
) -> list[ScoutResult]:
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
