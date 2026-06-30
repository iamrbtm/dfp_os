from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
import re
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    InventoryRecord,
    LicenseStatus,
    Order,
    OrderItem,
    OrderStatus,
    PosSale,
    PosSaleItem,
    PosSaleStatus,
    Product,
)
from app.models.trend import TrendSnapshot

INTERNAL_KEYWORDS = {
    "",
    "all",
    "main",
    "rss",
    "init_error",
    "pipeline_error",
    "not_configured",
    "configured",
    "analysis",
}

SOURCE_WEIGHTS = {
    "internal_demand": 1.6,
    "google_trends": 1.3,
    "etsy": 1.25,
    "makerworld": 1.15,
    "tiktok": 1.15,
    "printables": 1.1,
    "myminifactory": 1.0,
    "reddit": 0.95,
    "pinterest": 0.9,
    "bgg": 0.8,
}

METRIC_WEIGHTS = {
    "downloads": 0.22,
    "download_count": 0.22,
    "prints_count": 0.2,
    "print_count": 0.2,
    "makes": 0.2,
    "likes": 0.15,
    "num_favorers": 0.15,
    "favorites": 0.15,
    "saves": 0.14,
    "views": 0.08,
    "visits": 0.08,
    "impressions": 0.05,
    "comments": 0.08,
    "shares": 0.1,
    "interest": 0.05,
    "event_count": 0.35,
    "quantity": 0.45,
    "purchase_score": 0.6,
    "revenue": 0.08,
}

BUYER_SOURCE_WEIGHTS = {
    "internal_demand": 1.0,
    "etsy": 0.65,
    "google_trends": 0.35,
    "tiktok": 0.25,
    "reddit": 0.15,
    "pinterest": 0.15,
}

MAKER_SOURCES = {"makerworld", "printables", "myminifactory"}

LOCAL_FIT_TERMS = {
    "clarksville": 95,
    "tennessee": 90,
    "tn": 85,
    "military family": 85,
    "military": 70,
    "teacher": 82,
    "school": 78,
    "back to school": 84,
    "vendor": 82,
    "market": 78,
    "small business": 82,
    "business card": 78,
    "qr code": 78,
    "personalized": 76,
    "custom": 74,
    "name": 70,
    "gift": 68,
}

LICENSE_RISK_TERMS = {
    "disney",
    "pokemon",
    "marvel",
    "nintendo",
    "star wars",
    "harry potter",
    "fortnite",
    "minecraft",
    "bluey",
    "barbie",
    "taylor swift",
    "vols",
    "university of tennessee",
    "army logo",
    "military logo",
    "unit insignia",
}


@dataclass
class OpportunityCandidate:
    keyword: str
    title: str = ""
    current_product: bool = False
    product_id: int | None = None
    product_status: str = ""
    sources: set[str] = field(default_factory=set)
    item_count: int = 0
    signal_total: float = 0.0
    purchase_raw: float = 0.0
    velocity_raw: float = 0.0
    prices: list[float] = field(default_factory=list)
    maker_signal_count: int = 0
    trend_item_count: int = 0
    inventory_available: int = 0
    reorder_target: int = 0
    units_sold: int = 0
    revenue: float = 0.0
    base_price: float = 0.0
    estimated_profit: float = 0.0
    estimated_print_minutes: float = 0.0
    license_status: str = ""
    model_commercial_use_allowed: bool = False
    is_public: bool = False
    is_pos_visible: bool = False
    category: str = ""
    tags: str = ""

    @property
    def text(self) -> str:
        return " ".join(
            part
            for part in [
                self.keyword,
                self.title,
                self.category,
                self.tags,
            ]
            if part
        ).lower()


KEYWORD_PREFIXES = (
    "hot ",
    "category ",
    "3d printed ",
    "3d print ",
    "printed ",
    "printable ",
)


def _week_start(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _normalise_keyword(keyword: str | None) -> str:
    value = (keyword or "").strip().lower()
    value = value.replace("_", " ").replace("-", " ").replace("/", " ")
    value = re.sub(r"\s+", " ", value)

    changed = True
    while changed:
        changed = False
        for prefix in KEYWORD_PREFIXES:
            if value.startswith(prefix):
                value = value.removeprefix(prefix).strip()
                changed = True

    value = re.sub(r"\s+", " ", value)
    return "" if value in INTERNAL_KEYWORDS else value


def _item_keyword(row_keyword: str, item: dict[str, Any]) -> str:
    keyword = _normalise_keyword(str(item.get("keyword") or row_keyword))
    return keyword or _normalise_keyword(row_keyword)


def _parse_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    multiplier = 1.0
    if text.endswith("k"):
        multiplier = 1_000.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def _decimal_to_float(value: Decimal | int | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _clamp_score(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def _log_score(value: float, scale: float = 18.0) -> int:
    if value <= 0:
        return 0
    return _clamp_score(math.log1p(value) * scale)


def _item_signal_score(item: dict[str, Any]) -> float:
    score = 1.0
    for key, weight in METRIC_WEIGHTS.items():
        metric = _parse_number(item.get(key))
        if metric > 0:
            score += math.log1p(metric) * weight

    rank = _parse_number(item.get("rank"))
    if rank > 0:
        score += max(0.0, 2.0 - (rank / 25.0))

    return score


def _item_purchase_signal(source: str, item: dict[str, Any]) -> float:
    if source == "internal_demand":
        return (
            _parse_number(item.get("purchase_score"))
            + (_parse_number(item.get("quantity")) * 4)
            + (_parse_number(item.get("event_count")) * 2)
            + (_parse_number(item.get("revenue")) * 0.2)
        )
    if source == "etsy":
        return (
            _parse_number(item.get("num_favorers")) * 1.5
            + _parse_number(item.get("views")) * 0.1
            + _parse_number(item.get("price")) * 0.8
        )
    if source == "google_trends":
        return _parse_number(item.get("interest")) * 1.2
    if source == "tiktok":
        return (
            _parse_number(item.get("shares")) * 0.8
            + _parse_number(item.get("comments")) * 0.25
            + _parse_number(item.get("views")) * 0.015
        )
    return _item_signal_score(item) * BUYER_SOURCE_WEIGHTS.get(source, 0.1)


def _signal_rows(
    rows: list[TrendSnapshot],
) -> list[tuple[TrendSnapshot, dict[str, Any], str, list[dict[str, Any]]]]:
    signal_rows: list[tuple[TrendSnapshot, dict[str, Any], str, list[dict[str, Any]]]] = []
    for row in rows:
        payload = row.raw_metadata or {}
        if not isinstance(payload, dict):
            continue
        items = payload.get("items") or []
        if not isinstance(items, list) or not items:
            continue
        keyword = _normalise_keyword(row.keyword_or_category)
        if not keyword:
            continue
        signal_rows.append((row, payload, keyword, items))
    return signal_rows


def _source_weight(source: str) -> float:
    return SOURCE_WEIGHTS.get(source, 1.0)


def _keyword_velocity_scores(
    signal_rows: list[tuple[TrendSnapshot, dict[str, Any], str, list[dict[str, Any]]]],
) -> dict[str, float]:
    weekly_counts: dict[tuple[str, str], float] = defaultdict(float)
    for row, _payload, keyword, items in signal_rows:
        week_label = _week_start(row.scraped_at).isoformat()
        for item in items:
            item_keyword = _item_keyword(keyword, item)
            if item_keyword:
                weekly_counts[(item_keyword, week_label)] += _item_signal_score(
                    item
                ) * _source_weight(row.source)

    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (keyword, week), value in weekly_counts.items():
        grouped[keyword].append((week, value))

    velocity: dict[str, float] = {}
    for keyword, week_values in grouped.items():
        ordered = [value for _week, value in sorted(week_values)]
        if len(ordered) == 1:
            velocity[keyword] = ordered[0] * 0.3
            continue
        midpoint = len(ordered) // 2
        first_half = sum(ordered[:midpoint])
        second_half = sum(ordered[midpoint:])
        velocity[keyword] = max(0.0, second_half - first_half)
    return velocity


def _base_candidate(keyword: str) -> OpportunityCandidate:
    return OpportunityCandidate(keyword=keyword, title=keyword.title())


def _collect_signal_candidates(
    signal_rows: list[tuple[TrendSnapshot, dict[str, Any], str, list[dict[str, Any]]]],
) -> dict[str, OpportunityCandidate]:
    candidates: dict[str, OpportunityCandidate] = {}
    velocity_scores = _keyword_velocity_scores(signal_rows)

    for row, _payload, keyword, items in signal_rows:
        for item in items:
            item_keyword = _item_keyword(keyword, item)
            if not item_keyword:
                continue
            candidate = candidates.setdefault(item_keyword, _base_candidate(item_keyword))
            candidate.sources.add(row.source)
            candidate.item_count += 1
            candidate.trend_item_count += 1
            candidate.signal_total += _item_signal_score(item) * _source_weight(row.source)
            candidate.purchase_raw += _item_purchase_signal(row.source, item) * _source_weight(
                row.source
            )
            candidate.velocity_raw = max(
                candidate.velocity_raw, velocity_scores.get(item_keyword, 0.0)
            )
            if row.source in MAKER_SOURCES:
                candidate.maker_signal_count += 1
            price = _parse_number(item.get("price") or item.get("amount"))
            if price > 0:
                candidate.prices.append(price)
            if not candidate.title or candidate.title == item_keyword.title():
                candidate.title = str(item.get("title") or item_keyword.title())

    for candidate in candidates.values():
        if len(candidate.sources) > 1:
            multiplier = 1 + min(0.5, (len(candidate.sources) - 1) * 0.15)
            candidate.signal_total *= multiplier
            candidate.purchase_raw *= multiplier

    return candidates


def _catalog_metrics(db_session: Session, cutoff: datetime) -> dict[str, dict[int, Any]]:
    metrics: dict[str, dict[int, Any]] = {
        "inventory": {},
        "orders": {},
        "pos": {},
    }
    inventory_rows = (
        db_session.query(
            InventoryRecord.product_id,
            func.coalesce(func.sum(InventoryRecord.quantity_on_hand), 0),
            func.coalesce(func.sum(InventoryRecord.quantity_reserved), 0),
            func.coalesce(func.sum(InventoryRecord.reorder_target), 0),
        )
        .group_by(InventoryRecord.product_id)
        .all()
    )
    metrics["inventory"] = {
        product_id: {
            "available": int(on_hand or 0) - int(reserved or 0),
            "reorder_target": int(reorder_target or 0),
        }
        for product_id, on_hand, reserved, reorder_target in inventory_rows
    }

    order_rows = (
        db_session.query(
            OrderItem.product_id,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.line_total), 0),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.product_id.isnot(None),
            Order.created_at >= cutoff,
            Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.REFUNDED]),
        )
        .group_by(OrderItem.product_id)
        .all()
    )
    metrics["orders"] = {
        product_id: {"units": int(units or 0), "revenue": _decimal_to_float(revenue)}
        for product_id, units, revenue in order_rows
    }

    pos_rows = (
        db_session.query(
            PosSaleItem.product_id,
            func.coalesce(func.sum(PosSaleItem.quantity), 0),
            func.coalesce(func.sum(PosSaleItem.line_total), 0),
        )
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .filter(
            PosSaleItem.product_id.isnot(None),
            PosSale.created_at >= cutoff,
            PosSale.status == PosSaleStatus.COMPLETED,
        )
        .group_by(PosSaleItem.product_id)
        .all()
    )
    metrics["pos"] = {
        product_id: {"units": int(units or 0), "revenue": _decimal_to_float(revenue)}
        for product_id, units, revenue in pos_rows
    }
    return metrics


def _catalog_candidates(db_session: Session, cutoff: datetime) -> dict[str, OpportunityCandidate]:
    try:
        products = (
            db_session.query(Product)
            .filter(Product.deleted_at.is_(None))
            .order_by(Product.name)
            .all()
        )
        metrics = _catalog_metrics(db_session, cutoff)
    except Exception:
        return {}

    candidates: dict[str, OpportunityCandidate] = {}
    for product in products:
        keyword = _normalise_keyword(product.name)
        if not keyword:
            continue
        inventory = metrics["inventory"].get(product.id, {})
        order_metrics = metrics["orders"].get(product.id, {})
        pos_metrics = metrics["pos"].get(product.id, {})
        units_sold = int(order_metrics.get("units", 0)) + int(pos_metrics.get("units", 0))
        revenue = float(order_metrics.get("revenue", 0.0)) + float(pos_metrics.get("revenue", 0.0))
        candidate = OpportunityCandidate(
            keyword=keyword,
            title=product.name,
            current_product=True,
            product_id=product.id,
            product_status=(
                product.status.value if hasattr(product.status, "value") else str(product.status)
            ),
            sources={"catalog"},
            item_count=1,
            purchase_raw=(units_sold * 10) + (revenue * 0.35),
            inventory_available=int(inventory.get("available", 0)),
            reorder_target=int(inventory.get("reorder_target", 0)),
            units_sold=units_sold,
            revenue=revenue,
            base_price=_decimal_to_float(product.base_price),
            estimated_profit=_decimal_to_float(product.estimated_profit),
            estimated_print_minutes=_decimal_to_float(
                product.parsed_print_minutes or product.estimated_print_minutes
            ),
            license_status=(
                product.license_status.value
                if hasattr(product.license_status, "value")
                else str(product.license_status)
            ),
            model_commercial_use_allowed=bool(product.model_commercial_use_allowed),
            is_public=bool(product.is_public),
            is_pos_visible=bool(product.is_pos_visible),
            category=product.category.name if product.category else "",
            tags=product.tags or "",
        )
        if candidate.base_price > 0:
            candidate.prices.append(candidate.base_price)
        candidates[keyword] = candidate
    return candidates


def _merge_catalog_candidates(
    candidates: dict[str, OpportunityCandidate],
    catalog_candidates: dict[str, OpportunityCandidate],
) -> dict[str, OpportunityCandidate]:
    for keyword, product_candidate in catalog_candidates.items():
        existing = candidates.get(keyword)
        if existing is None:
            candidates[keyword] = product_candidate
            continue
        existing.current_product = True
        existing.product_id = product_candidate.product_id
        existing.product_status = product_candidate.product_status
        existing.title = product_candidate.title
        existing.sources.update(product_candidate.sources)
        existing.item_count += product_candidate.item_count
        existing.purchase_raw += product_candidate.purchase_raw
        existing.prices.extend(product_candidate.prices)
        existing.inventory_available = product_candidate.inventory_available
        existing.reorder_target = product_candidate.reorder_target
        existing.units_sold = product_candidate.units_sold
        existing.revenue = product_candidate.revenue
        existing.base_price = product_candidate.base_price
        existing.estimated_profit = product_candidate.estimated_profit
        existing.estimated_print_minutes = product_candidate.estimated_print_minutes
        existing.license_status = product_candidate.license_status
        existing.model_commercial_use_allowed = product_candidate.model_commercial_use_allowed
        existing.is_public = product_candidate.is_public
        existing.is_pos_visible = product_candidate.is_pos_visible
        existing.category = product_candidate.category
        existing.tags = product_candidate.tags
    return candidates


def _price_resilience(candidate: OpportunityCandidate) -> int:
    if candidate.current_product and candidate.base_price > 0:
        margin = candidate.estimated_profit / candidate.base_price if candidate.base_price else 0
        price_score = 35 + min(candidate.base_price, 60) * 0.7
        margin_score = max(-20, min(35, margin * 70))
        return _clamp_score(price_score + margin_score)
    if candidate.prices:
        avg_price = sum(candidate.prices) / len(candidate.prices)
        return _clamp_score(30 + min(avg_price, 75) * 0.8)
    return 50


def _low_saturation(candidate: OpportunityCandidate) -> int:
    if candidate.trend_item_count == 0 and candidate.current_product:
        return 65 if candidate.units_sold > 0 else 50
    score = 82 - (candidate.trend_item_count * 2.5) - (candidate.maker_signal_count * 6)
    if len(candidate.sources - MAKER_SOURCES) > 1:
        score += 8
    return _clamp_score(score)


def _local_fit(candidate: OpportunityCandidate) -> int:
    score = 45
    text = candidate.text
    for term, term_score in LOCAL_FIT_TERMS.items():
        if term in text:
            score = max(score, term_score)
    return _clamp_score(score)


def _production_fit(candidate: OpportunityCandidate) -> int:
    if not candidate.current_product:
        text = candidate.text
        if any(term in text for term in ("keychain", "magnet", "ornament", "tag", "sign")):
            return 78
        if any(term in text for term in ("dragon", "dice tower", "organizer", "holder")):
            return 68
        return 55

    minutes = candidate.estimated_print_minutes
    if minutes <= 0:
        score = 55
    elif minutes <= 60:
        score = 92
    elif minutes <= 180:
        score = 78
    elif minutes <= 360:
        score = 62
    else:
        score = 45

    if candidate.estimated_profit > 0:
        score += min(12, candidate.estimated_profit)
    if candidate.is_public or candidate.is_pos_visible:
        score += 4
    return _clamp_score(score)


def _license_risk(candidate: OpportunityCandidate) -> int:
    text = candidate.text
    if any(term in text for term in LICENSE_RISK_TERMS):
        return 90
    if not candidate.current_product:
        return 25

    status = candidate.license_status
    if status in {LicenseStatus.COMMERCIAL_ALLOWED.value, LicenseStatus.CUSTOMER_OWNED.value}:
        return 5
    if status == LicenseStatus.COMMERCIAL_SUBSCRIPTION.value:
        return 18
    if status == LicenseStatus.PERSONAL_ONLY.value:
        return 85
    if status == LicenseStatus.RESTRICTED.value:
        return 95
    if status == LicenseStatus.NEEDS_REVIEW.value:
        return 72
    if status == LicenseStatus.RETIRED.value:
        return 80
    if candidate.model_commercial_use_allowed:
        return 10
    return 45


def _recommend_action(candidate: OpportunityCandidate, scores: dict[str, int]) -> str:
    if scores["license_risk"] >= 70:
        return "license_review"
    if candidate.current_product:
        demand = scores["purchase_intent"] + scores["trend_velocity"]
        low_inventory = candidate.inventory_available <= max(2, candidate.reorder_target)
        if scores["opportunity_score"] >= 70 and low_inventory:
            return "print_now"
        if scores["opportunity_score"] >= 65:
            return "keep_selling"
        if demand < 45 and candidate.inventory_available > 0:
            return "clearance_candidate"
        if demand < 35 and candidate.inventory_available <= 0:
            return "retire_review"
        return "improve_or_monitor"
    if scores["opportunity_score"] >= 65:
        return "test_product"
    if scores["opportunity_score"] >= 45:
        return "monitor"
    return "low_priority"


def _score_candidate(candidate: OpportunityCandidate) -> dict[str, Any]:
    purchase_intent = _log_score(candidate.purchase_raw, scale=18.0)
    if candidate.current_product and candidate.units_sold == 0 and candidate.purchase_raw == 0:
        purchase_intent = 8
    trend_velocity = _log_score(candidate.velocity_raw, scale=20.0)
    if candidate.signal_total > 0 and trend_velocity == 0:
        trend_velocity = min(45, _log_score(candidate.signal_total, scale=10.0))

    scores = {
        "purchase_intent": purchase_intent,
        "trend_velocity": trend_velocity,
        "price_resilience": _price_resilience(candidate),
        "low_saturation": _low_saturation(candidate),
        "local_fit": _local_fit(candidate),
        "production_fit": _production_fit(candidate),
        "license_risk": _license_risk(candidate),
    }
    opportunity_score = _clamp_score(
        (scores["purchase_intent"] * 0.30)
        + (scores["trend_velocity"] * 0.18)
        + (scores["price_resilience"] * 0.14)
        + (scores["low_saturation"] * 0.12)
        + (scores["local_fit"] * 0.10)
        + (scores["production_fit"] * 0.12)
        - (scores["license_risk"] * 0.16)
    )
    scores["opportunity_score"] = opportunity_score

    action = _recommend_action(candidate, scores)
    return {
        "keyword": candidate.keyword,
        "title": candidate.title or candidate.keyword.title(),
        "score": opportunity_score,
        "opportunity_score": opportunity_score,
        "purchase_intent": scores["purchase_intent"],
        "trend_velocity": scores["trend_velocity"],
        "price_resilience": scores["price_resilience"],
        "low_saturation": scores["low_saturation"],
        "local_fit": scores["local_fit"],
        "production_fit": scores["production_fit"],
        "license_risk": scores["license_risk"],
        "action": action,
        "candidate_type": "current_product" if candidate.current_product else "potential_product",
        "current_product": candidate.current_product,
        "product_id": candidate.product_id,
        "product_status": candidate.product_status,
        "sources": sorted(candidate.sources),
        "item_count": candidate.item_count,
        "inventory_available": candidate.inventory_available,
        "reorder_target": candidate.reorder_target,
        "units_sold": candidate.units_sold,
        "revenue": round(candidate.revenue, 2),
        "base_price": round(candidate.base_price, 2),
        "license_status": candidate.license_status,
    }


def compute_velocity_and_momentum(db_session: Session, lookback_weeks: int = 8) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)

    rows = db_session.query(TrendSnapshot).filter(TrendSnapshot.scraped_at >= cutoff).all()
    signal_rows = _signal_rows(rows)

    weekly_counts: dict[tuple[str, str, str], float] = defaultdict(float)
    source_keywords: dict[str, set[str]] = defaultdict(set)

    for row, _payload, keyword, items in signal_rows:
        week_label = _week_start(row.scraped_at).isoformat()
        for item in items:
            item_keyword = _item_keyword(keyword, item)
            if not item_keyword:
                continue
            key = (row.source, item_keyword, week_label)
            weekly_counts[key] += _item_signal_score(item) * _source_weight(row.source)
            source_keywords[row.source].add(item_keyword)

    velocity: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for (source, keyword, week), count in sorted(weekly_counts.items()):
        velocity[source][keyword].append({"week": week, "count": round(count, 2)})

    trends: dict[str, Any] = {
        "velocity": velocity,
        "momentum": {},
        "cross_source": {},
        "metadata": {
            "lookback_weeks": lookback_weeks,
            "total_rows": len(rows),
            "signal_rows": len(signal_rows),
        },
    }

    for source, keywords in velocity.items():
        for keyword, weeks in keywords.items():
            if len(weeks) >= 2:
                first_half = sum(w["count"] for w in weeks[: len(weeks) // 2])
                second_half = sum(w["count"] for w in weeks[len(weeks) // 2 :])
                delta = second_half - first_half
                trends["momentum"].setdefault(source, {})[keyword] = {
                    "first_half_total": round(first_half, 2),
                    "second_half_total": round(second_half, 2),
                    "delta": round(delta, 2),
                    "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
                }

    keyword_sources: dict[str, set[str]] = defaultdict(set)
    for source, keywords in source_keywords.items():
        for kw in keywords:
            keyword_sources[kw].add(source)

    cross_source = {
        kw: sorted(sources) for kw, sources in keyword_sources.items() if len(sources) > 1
    }
    trends["cross_source"] = {
        "appearing_across_multiple_sources": cross_source,
        "total_cross_source_keywords": len(cross_source),
    }

    return trends


def compute_top_opportunities(db_session: Session, lookback_weeks: int = 4) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)

    rows = db_session.query(TrendSnapshot).filter(TrendSnapshot.scraped_at >= cutoff).all()
    signal_rows = _signal_rows(rows)
    candidates = _collect_signal_candidates(signal_rows)
    catalog_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    _merge_catalog_candidates(candidates, _catalog_candidates(db_session, catalog_cutoff))

    scored = [_score_candidate(candidate) for candidate in candidates.values()]
    scored = [item for item in scored if item["opportunity_score"] > 0]
    scored.sort(
        key=lambda item: (
            -item["opportunity_score"],
            item["license_risk"],
            item["keyword"],
        )
    )
    for index, item in enumerate(scored[:50], start=1):
        item["rank"] = index
    return scored[:50]
