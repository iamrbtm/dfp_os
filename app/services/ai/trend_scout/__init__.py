from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests

from app.extensions import db
from app.models.trend import TrendOpportunityScore, TrendReport, TrendSnapshot
from app.services.ai.trend_scout.analyzer import run_analysis
from app.services.ai.trend_scout.sources import (
    RateLimiter,
    ScoutResult,
    fetch_myminifactory,
    fetch_etsy,
    fetch_bgg,
    fetch_google_trends,
    fetch_internal_demand,
    fetch_makerworld,
    fetch_printables,
    fetch_reddit,
    fetch_pinterest,
    fetch_tiktok,
)

logger = logging.getLogger(__name__)

DB_FETCHERS = {
    "internal_demand": fetch_internal_demand,
}

EXTERNAL_FETCHERS = {
    "myminifactory": fetch_myminifactory,
    "bgg": fetch_bgg,
    "makerworld": fetch_makerworld,
    "printables": fetch_printables,
    "reddit": fetch_reddit,
    "etsy": fetch_etsy,
    "pinterest": fetch_pinterest,
    "google_trends": fetch_google_trends,
    "tiktok": fetch_tiktok,
}

FETCHERS = {**DB_FETCHERS, **EXTERNAL_FETCHERS}


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


def _source_health_from_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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


def run_all_sources(progress_callback=None) -> list[dict[str, Any]]:
    all_results: list[ScoutResult] = []
    total_sources = len(FETCHERS)
    pipeline_total = total_sources + 1
    completed = 0

    for name, fetcher in DB_FETCHERS.items():
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

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(_run_fetcher, name, fn, RateLimiter()): name
            for name, fn in EXTERNAL_FETCHERS.items()
        }
        for future in as_completed(future_map):
            name = future_map[future]
            completed += 1
            try:
                batch = future.result(timeout=120)
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


def _parse_scraped_at(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_full_pipeline(
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
    progress_callback=None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    total_inserted = 0
    failed_sources: set[str] = set()
    successful_sources: set[str] = set()

    if progress_callback:
        progress_callback(0, len(FETCHERS) + 1, "initializing", "running")

    scraped = run_all_sources(progress_callback=progress_callback)

    for snapshot in scraped:
        source = snapshot.get("source", "unknown")
        keyword = snapshot.get("keyword_or_category", "unknown")
        errors = snapshot.get("errors", [])

        if errors:
            failed_sources.add(f"{source}/{keyword}: {'; '.join(errors)}")
        if snapshot.get("items"):
            successful_sources.add(source)

        record = TrendSnapshot(
            source=source,
            keyword_or_category=keyword,
            scraped_at=_parse_scraped_at(snapshot.get("scraped_at"), now),
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

    source_health = _source_health_from_results(scraped)

    report = run_analysis(
        db_session=db.session,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        source_health=source_health,
    )
    report_id = report.id if report else None

    try:
        _create_pipeline_notifications(report_id, failed_sources)
    except Exception:
        logger.exception("Failed to create pipeline notifications")

    return {
        "success": True,
        "total_snapshots": total_inserted,
        "failed_sources": sorted(failed_sources),
        "successful_sources": sorted(successful_sources),
        "report_id": report_id,
        "source_health": source_health,
    }


def _create_pipeline_notifications(
    report_id: int | None,
    failed_sources: set[str],
) -> None:
    from app.services.notification import create_notification

    if failed_sources:
        source_list = ", ".join(sorted(failed_sources)[:5])
        create_notification(
            notification_type="trend_scout_source_failure",
            title="Trend Scout source failures",
            message=f"Pipeline completed but {len(failed_sources)} source(s) had errors: {source_list}",
            link="/admin/trend-scout/monitor" if report_id else None,
        )

    if report_id is not None:
        print_now = (
            db.session.query(TrendOpportunityScore)
            .filter(
                TrendOpportunityScore.report_id == report_id,
                TrendOpportunityScore.action == "print_now",
            )
            .count()
        )
        if print_now:
            create_notification(
                notification_type="trend_scout_print_now",
                title=f"{print_now} product(s) ready to print",
                message=f"Trend Scout found {print_now} product(s) flagged as print_now. Check the latest report for details.",
                link="/admin/trend-scout/reports",
            )
