from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models import InternalDemandEvent, Product
from app.services.ai.trend_scout.sources._base import ScoutResult

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


def _event_keyword(event: InternalDemandEvent) -> str:
    if event.keyword:
        return event.keyword
    if event.product:
        return event.product.name.lower()
    return "unclassified internal demand"


def fetch_internal_demand(session: Any = None, limiter: Any = None) -> list[ScoutResult]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    events = (
        db.session.query(InternalDemandEvent)
        .filter(InternalDemandEvent.occurred_at >= cutoff)
        .order_by(InternalDemandEvent.occurred_at.desc())
        .all()
    )

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
        keyword = _event_keyword(event)
        bucket = grouped[keyword]
        event_type = (
            event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
        )
        quantity = int(event.quantity or 0)
        value = _decimal(event.value)
        bucket["event_counts"][event_type] += 1
        bucket["quantity"] += quantity
        bucket["value"] += value
        bucket["weighted_score"] += EVENT_WEIGHTS.get(event_type, 1.0) * max(quantity, 1)
        bucket["terms"].update(event.extracted_terms or [])
        if event.product_id:
            bucket["product_ids"].add(event.product_id)
        bucket["events"].append(event)

    result = ScoutResult(source="internal_demand", keyword_or_category="buyer_intent")
    result.metadata = {
        "lookback_days": LOOKBACK_DAYS,
        "total_events": len(events),
        "total_keywords": len(grouped),
    }

    for keyword, bucket in sorted(
        grouped.items(),
        key=lambda item: (-item[1]["weighted_score"], item[0]),
    ):
        sample_event = bucket["events"][0]
        product = (
            db.session.get(Product, sample_event.product_id) if sample_event.product_id else None
        )
        result.items.append(
            {
                "title": product.name if product else keyword,
                "keyword": keyword,
                "event_count": len(bucket["events"]),
                "event_counts": dict(bucket["event_counts"]),
                "quantity": bucket["quantity"],
                "revenue": float(bucket["value"]),
                "purchase_score": round(bucket["weighted_score"], 2),
                "extracted_terms": sorted(bucket["terms"])[:12],
                "product_ids": sorted(bucket["product_ids"]),
                "category": product.category.name if product and product.category else "",
            }
        )

    if not result.items:
        result.metadata["note"] = "No internal demand events recorded in the lookback window."

    return [result]
