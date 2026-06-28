from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from app.extensions import db
from app.models.trend import TrendSnapshot
from app.services.ai.trend_scout.analyzer import run_analysis
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

logger = logging.getLogger(__name__)

FETCHERS = {
    "myminifactory": fetch_myminifactory,
    "bgg": fetch_bgg,
    "makerworld": fetch_makerworld,
    "printables": fetch_printables,
    "reddit": fetch_reddit,
    "etsy": fetch_etsy,
}


def _run_fetcher(name: str, fetcher, limiter: RateLimiter) -> list[ScoutResult]:
    try:
        with requests.Session() as session:
            return fetcher(session, limiter)
    except Exception as exc:
        logger.warning("Fetcher %s failed: %s", name, exc)
        return [
            ScoutResult(
                source=name,
                keyword_or_category="pipeline_error",
                errors=[str(exc)],
            )
        ]


def run_all_sources() -> list[dict[str, Any]]:
    limiter = RateLimiter()
    all_results: list[ScoutResult] = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(_run_fetcher, name, fn, limiter): name
            for name, fn in FETCHERS.items()
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                batch = future.result(timeout=120)
                all_results.extend(batch)
            except Exception as exc:
                logger.error("Fetcher %s timed out or crashed: %s", name, exc)
                all_results.append(
                    ScoutResult(
                        source=name,
                        keyword_or_category="pipeline_error",
                        errors=[f"Fetcher crashed: {exc}"],
                    )
                )

    return [r.to_dict() for r in all_results]


def run_full_pipeline(
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    total_inserted = 0
    failed_sources: list[str] = []

    scraped = run_all_sources()

    for snapshot in scraped:
        source = snapshot.get("source", "unknown")
        keyword = snapshot.get("keyword_or_category", "unknown")
        errors = snapshot.get("errors", [])

        if errors:
            failed_sources.append(f"{source}/{keyword}: {'; '.join(errors)}")

        record = TrendSnapshot(
            source=source,
            keyword_or_category=keyword,
            scraped_at=now,
            raw_metadata=snapshot,
        )
        db.session.add(record)
        total_inserted += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("DB commit failed for snapshots: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "total_snapshots": 0,
            "report_id": None,
        }

    logger.info(
        "Scrape done: %d snapshots committed, %d source errors",
        total_inserted,
        len(failed_sources),
    )

    report = run_analysis(
        db_session=db.session,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
    )

    return {
        "success": True,
        "total_snapshots": total_inserted,
        "failed_sources": failed_sources,
        "report_id": report.id if report else None,
    }
