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
    fetch_pinterest,
)

logger = logging.getLogger(__name__)

FETCHERS = {
    "myminifactory": fetch_myminifactory,
    "bgg": fetch_bgg,
    "makerworld": fetch_makerworld,
    "printables": fetch_printables,
    "reddit": fetch_reddit,
    "etsy": fetch_etsy,
    "pinterest": fetch_pinterest,
}


def _run_fetcher(name: str, fetcher, limiter: RateLimiter) -> list[ScoutResult]:
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


def run_all_sources(progress_callback=None) -> list[dict[str, Any]]:
    limiter = RateLimiter()
    all_results: list[ScoutResult] = []
    total = len(FETCHERS)
    completed = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(_run_fetcher, name, fn, limiter): name for name, fn in FETCHERS.items()
        }
        for future in as_completed(future_map):
            name = future_map[future]
            completed += 1
            try:
                batch = future.result(timeout=120)
                all_results.extend(batch)
                logger.info("[%s] Fetcher completed successfully (%d/%d)", name, completed, total)
                if progress_callback:
                    progress_callback(completed, total, name, "completed")
            except Exception as exc:
                logger.error(
                    "[%s] Fetcher timed out or crashed: %s (%d/%d)", name, exc, completed, total
                )
                if progress_callback:
                    progress_callback(completed, total, name, "failed")
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
    progress_callback=None,
) -> dict[str, Any]:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    total_inserted = 0
    failed_sources: list[str] = []

    if progress_callback:
        progress_callback(0, len(FETCHERS) + 1, "initializing", "running")

    scraped = run_all_sources(progress_callback=progress_callback)

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

    if progress_callback:
        progress_callback(len(FETCHERS) + 1, len(FETCHERS) + 1, "analysis", "running")

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
