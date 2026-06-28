from __future__ import annotations

from typing import Any

import requests

from app.services.ai.trend_scout.sources import (
    RateLimiter,
    ScoutResult,
    fetch_myminifactory,
    fetch_etsy,
    fetch_bgg,
    fetch_makerworld,
    fetch_printables,
    fetch_reddit,
)

FETCHERS = {
    "myminifactory": fetch_myminifactory,
    "bgg": fetch_bgg,
    "makerworld": fetch_makerworld,
    "printables": fetch_printables,
    "reddit": fetch_reddit,
    "etsy": fetch_etsy,
}


def run_all_sources() -> list[dict[str, Any]]:
    limiter = RateLimiter()
    results: list[ScoutResult] = []

    with requests.Session() as session:
        for source_name, fetcher in FETCHERS.items():
            try:
                batch = fetcher(session, limiter)
                results.extend(batch)
            except Exception as exc:
                results.append(
                    ScoutResult(
                        source=source_name,
                        keyword_or_category="pipeline_error",
                        errors=[str(exc)],
                    )
                )

    return [r.to_dict() for r in results]
