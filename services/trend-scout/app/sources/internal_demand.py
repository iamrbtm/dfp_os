"""Internal demand fetcher for the Trend Scout microservice.

Reads InternalDemandEvent / Product / Category aggregates from the main Flask app
over the internal /api/internal/internal-demand endpoint (added in Phase 6).

Until that endpoint exists the fetcher returns a structured "not_configured"
result so the source health row surfaces the gap rather than crashing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.sources._base import ScoutResult

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 90

EVENT_WEIGHTS = {
    "storefront_search_performed": 1.5,
    "product_viewed": 1.0,
    "product_added_to_cart": 4.0,
    "cart_updated": 2.0,
    "cart_removed": -1.0,
    "checkout_started": 6.0,
    "online_order_created": 12.0,
    "custom_request_submitted": 10.0,
    "pos_sale_completed": 14.0,
    "manual_customer_request_logged": 10.0,
}


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _event_keyword(event: dict[str, Any]) -> str:
    if event.get("keyword"):
        return event["keyword"]
    product = event.get("product") or {}
    if product.get("name"):
        return product["name"].lower()
    return "unclassified internal demand"


def fetch_internal_demand(
    session: Any = None,
    limiter: Any = None,
    lookback_days: int = LOOKBACK_DAYS,
    flask_base_url: str | None = None,
    flask_token: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[ScoutResult]:
    """Fetch aggregated internal buyer intent signals.

    Synchronous wrapper preserved for compatibility with the existing fetcher
    pipeline contract (which expects ``(session, limiter)`` signature). Internally
    it delegates to an async coroutine via ``asyncio.run`` when no event loop
    is already running.
    """

    base_url = (
        flask_base_url or os.getenv("TREND_SCOUT_FLASK_BASE_URL") or os.getenv("APP_BASE_URL") or "http://web:5000"
    )
    token = flask_token or os.getenv("TREND_SCOUT_FLASK_INTERNAL_TOKEN", "")

    if not token:
        result = ScoutResult(
            source="internal_demand",
            keyword_or_category="not_configured",
            errors=["TREND_SCOUT_FLASK_INTERNAL_TOKEN not set; internal demand endpoint requires authentication"],
        )
        result.metadata["note"] = (
            "Set TREND_SCOUT_FLASK_INTERNAL_TOKEN (shared with the Flask app) "
            "and ensure the Flask /api/internal/internal-demand endpoint is reachable."
        )
        return [result]

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                _fetch_internal_demand_async(
                    base_url=base_url,
                    token=token,
                    lookback_days=lookback_days,
                    timeout_seconds=timeout_seconds,
                )
            )
        return asyncio.run(
            _fetch_internal_demand_async(
                base_url=base_url,
                token=token,
                lookback_days=lookback_days,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        logger.warning("[internal_demand] Fetcher FAILED: %s", exc)
        result = ScoutResult(
            source="internal_demand",
            keyword_or_category="pipeline_error",
            errors=[str(exc)],
        )
        return [result]


async def _fetch_internal_demand_async(
    base_url: str,
    token: str,
    lookback_days: int,
    timeout_seconds: float,
) -> list[ScoutResult]:
    url = f"{base_url.rstrip('/')}/api/internal/internal-demand"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {"lookback_days": lookback_days}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            logger.warning("[internal_demand] HTTP error: %s", exc)
            return [
                ScoutResult(
                    source="internal_demand",
                    keyword_or_category="pipeline_error",
                    errors=[str(exc)],
                )
            ]

    if resp.status_code != 200:
        result = ScoutResult(
            source="internal_demand",
            keyword_or_category="pipeline_error",
            errors=[f"HTTP {resp.status_code} from {url}"],
        )
        return [result]

    payload = resp.json() or {}
    events = payload.get("events") or []
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "events": [],
            "event_counts": defaultdict(int),
            "quantity": 0,
            "value": Decimal("0"),
            "weighted_score": 0.0,
            "terms": set(),
            "product_ids": set(),
        }
    )

    for event in events:
        if event.get("occurred_at"):
            try:
                occurred_at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            except ValueError:
                occurred_at = None
            if occurred_at and occurred_at < cutoff:
                continue
        keyword = _event_keyword(event)
        bucket = grouped[keyword]
        event_type = event.get("event_type", "")
        quantity = int(event.get("quantity") or 0)
        value = _decimal(event.get("value"))
        bucket["event_counts"][event_type] += 1
        bucket["quantity"] += quantity
        bucket["value"] += value
        bucket["weighted_score"] += EVENT_WEIGHTS.get(event_type, 1.0) * max(quantity, 1)
        bucket["terms"].update(event.get("extracted_terms") or [])
        if event.get("product_id"):
            bucket["product_ids"].add(event["product_id"])
        bucket["events"].append(event)

    result = ScoutResult(source="internal_demand", keyword_or_category="buyer_intent")
    result.metadata = {
        "lookback_days": lookback_days,
        "total_events": len(events),
        "total_keywords": len(grouped),
    }

    for keyword, bucket in sorted(
        grouped.items(),
        key=lambda item: (-item[1]["weighted_score"], item[0]),
    ):
        sample_event = bucket["events"][0]
        product = sample_event.get("product") or {}
        result.items.append(
            {
                "title": product.get("name") or keyword,
                "keyword": keyword,
                "event_count": len(bucket["events"]),
                "event_counts": dict(bucket["event_counts"]),
                "quantity": bucket["quantity"],
                "revenue": float(bucket["value"]),
                "purchase_score": round(bucket["weighted_score"], 2),
                "extracted_terms": sorted(bucket["terms"])[:12],
                "product_ids": sorted(bucket["product_ids"]),
                "category": product.get("category_name", ""),
            }
        )

    if not result.items:
        result.metadata["note"] = "No internal demand events recorded in the lookback window."

    return [result]
