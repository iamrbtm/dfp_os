"""Internal API endpoints for the Trend Scout microservice.

This blueprint exposes /api/internal/* to the microservice for cross-service
data flow. Today it covers buyer-intent aggregation (so the
``internal_demand`` source can read aggregated signals without touching the
main DB) and aggregated order + PosSale data (so the backtest's
actual-sales provider can score past opportunities).

All endpoints require the same ``TREND_SCOUT_INTERNAL_API_TOKEN`` Bearer
header that the microservice uses; this is the only token the main app
exposes to the microservice.
"""

from __future__ import annotations

import hmac
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app, jsonify, request

from app.blueprints.internal_api import bp
from app.extensions import db
from app.models import InternalDemandEvent, Product

logger = logging.getLogger(__name__)


def _is_authorized() -> bool:
    header = request.headers.get("Authorization", "")
    token = current_app.config.get("TREND_SCOUT_INTERNAL_API_TOKEN", "")
    expected = f"Bearer {token}"
    return hmac.compare_digest(header, expected)


@bp.before_request
def _require_internal_token():
    if request.method == "OPTIONS":
        return None
    if not _is_authorized():
        return jsonify({"code": "unauthorized", "message": "Invalid internal token"}), 401


@bp.get("/internal-demand")
def aggregated_internal_demand():
    """Return aggregated InternalDemandEvent + Product rows from the last N days.

    Query params:
        lookback_days: integer, default 90
    """
    try:
        lookback_days = int(request.args.get("lookback_days", 90))
    except ValueError:
        return jsonify({"code": "bad_request", "message": "lookback_days must be an integer"}), 400
    lookback_days = max(1, min(lookback_days, 365))

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    events = (
        db.session.query(InternalDemandEvent)
        .filter(InternalDemandEvent.occurred_at >= cutoff)
        .order_by(InternalDemandEvent.occurred_at.desc())
        .all()
    )
    product_ids = {e.product_id for e in events if e.product_id}
    products: dict[Any, Product] = {}
    if product_ids:
        for p in db.session.query(Product).filter(Product.id.in_(product_ids)).all():
            products[p.id] = p

    out: list[dict[str, Any]] = []
    for event in events:
        product = products.get(event.product_id) if event.product_id else None
        out.append(
            {
                "id": event.id,
                "event_type": getattr(event.event_type, "value", str(event.event_type)),
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                "keyword": event.keyword,
                "product_id": event.product_id,
                "product": (
                    {
                        "name": product.name if product else None,
                        "category_name": (
                            product.category.name if product and product.category else None
                        ),
                    }
                    if product
                    else None
                ),
                "quantity": int(event.quantity or 0),
                "value": float(event.value or 0.0),
                "extracted_terms": event.extracted_terms or [],
            }
        )

    return jsonify({"events": out, "lookback_days": lookback_days, "count": len(out)})


@bp.get("/orders-since")
def orders_since():
    """Return aggregated order/PosSale items since the given date.

    Used by the backtest's actual-sales provider (Phase 6).

    Query params:
        since_days: integer, default 60
    """
    try:
        since_days = int(request.args.get("since_days", 60))
    except ValueError:
        return jsonify({"code": "bad_request", "message": "since_days must be an integer"}), 400
    since_days = max(1, min(since_days, 365))
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    from app.models.order import Order, OrderItem
    from app.models.pos import PosSale, PosSaleItem

    orders = (
        db.session.query(Order, OrderItem)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(Order.created_at >= cutoff)
        .all()
    )
    pos_sales = (
        db.session.query(PosSale, PosSaleItem)
        .join(PosSaleItem, PosSaleItem.pos_sale_id == PosSale.id)
        .filter(PosSale.created_at >= cutoff)
        .all()
    )

    aggregate: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"quantity": 0, "revenue": 0.0, "order_count": 0, "channel": "online"}
    )

    for order, item in orders:
        pid = item.product_id
        if pid is None:
            continue
        aggregate[pid]["quantity"] += int(item.quantity or 0)
        aggregate[pid]["revenue"] += float(item.total_price or 0.0)
        aggregate[pid]["order_count"] += 1

    for sale, item in pos_sales:
        pid = item.product_id
        if pid is None:
            continue
        aggregate[pid]["quantity"] += int(item.quantity or 0)
        aggregate[pid]["revenue"] += float(item.line_total or 0.0)
        aggregate[pid]["order_count"] += 1
        aggregate[pid]["channel"] = "pos"

    return jsonify(
        {
            "by_product": dict(aggregate),
            "since_days": since_days,
        }
    )


@bp.get("/health")
def internal_health():
    """Liveness probe for the main app reachable from the microservice."""
    return jsonify({"status": "ok", "service": "dfp-os-internal-api"})
