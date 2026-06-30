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
from app.services.trend_match import (  # noqa: F811
    match_product_to_term,
)

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
    match_confidence: str = ""
    sell_through_rate: float = 0.0
    days_since_last_sale: int = 999
    inventory_age_days: int = 0
    stockout_detected: bool = False
    margin_pct: float = 0.0
    last_sale_at: str | None = None

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
        "last_sale": {},
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
            func.max(Order.created_at),
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
        product_id: {
            "units": int(units or 0),
            "revenue": _decimal_to_float(revenue),
            "last_sale": last_sale.isoformat() if last_sale else None,
        }
        for product_id, units, revenue, last_sale in order_rows
    }

    pos_rows = (
        db_session.query(
            PosSaleItem.product_id,
            func.coalesce(func.sum(PosSaleItem.quantity), 0),
            func.coalesce(func.sum(PosSaleItem.line_total), 0),
            func.max(PosSale.created_at),
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
        product_id: {
            "units": int(units or 0),
            "revenue": _decimal_to_float(revenue),
            "last_sale": last_sale.isoformat() if last_sale else None,
        }
        for product_id, units, revenue, last_sale in pos_rows
    }

    all_product_ids = set(metrics["orders"]) | set(metrics["pos"])
    for pid in all_product_ids:
        order_last = metrics["orders"].get(pid, {}).get("last_sale")
        pos_last = metrics["pos"].get(pid, {}).get("last_sale")
        metrics["last_sale"][pid] = max(
            [d for d in [order_last, pos_last] if d is not None],
            default=None,
        )

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

    now = datetime.now(timezone.utc)
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
        available = int(inventory.get("available", 0))
        base_price = _decimal_to_float(product.base_price)
        estimated_profit = _decimal_to_float(product.estimated_profit)
        total_units = units_sold + available

        sell_through_rate = 0.0
        if total_units > 0:
            sell_through_rate = round(units_sold / total_units, 4)

        last_sale_str = metrics["last_sale"].get(product.id)
        days_since_last_sale = 999
        if last_sale_str:
            try:
                last_dt = datetime.fromisoformat(last_sale_str)
                days_since_last_sale = (now - last_dt).days
            except (ValueError, TypeError):
                pass

        inventory_age_days = 0
        if product.created_at:
            inventory_age_days = (now - product.created_at).days

        margin_pct = 0.0
        if base_price > 0:
            margin_pct = round(estimated_profit / base_price, 4)

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
            inventory_available=available,
            reorder_target=int(inventory.get("reorder_target", 0)),
            units_sold=units_sold,
            revenue=revenue,
            base_price=base_price,
            estimated_profit=estimated_profit,
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
            sell_through_rate=sell_through_rate,
            days_since_last_sale=days_since_last_sale,
            inventory_age_days=inventory_age_days,
            stockout_detected=(available <= 0 and units_sold > 0),
            margin_pct=margin_pct,
            last_sale_at=last_sale_str,
        )
        if candidate.base_price > 0:
            candidate.prices.append(candidate.base_price)
        candidates[keyword] = candidate
    return candidates


def _merge_catalog_candidates(
    candidates: dict[str, OpportunityCandidate],
    catalog_candidates: dict[str, OpportunityCandidate],
    products: list[Product] | None = None,
) -> dict[str, OpportunityCandidate]:
    exact_matched_keys: set[str] = set()
    for keyword, product_candidate in catalog_candidates.items():
        existing = candidates.get(keyword)
        if existing is None:
            continue
        exact_matched_keys.add(keyword)
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
        existing.match_confidence = "exact"
        existing.sell_through_rate = product_candidate.sell_through_rate
        existing.days_since_last_sale = product_candidate.days_since_last_sale
        existing.inventory_age_days = product_candidate.inventory_age_days
        existing.stockout_detected = product_candidate.stockout_detected
        existing.margin_pct = product_candidate.margin_pct
        existing.last_sale_at = product_candidate.last_sale_at

    if products:
        product_by_id = {p.id: p for p in products}
        for signal_key, signal_candidate in candidates.items():
            if signal_candidate.current_product:
                continue
            best_product = None
            best_confidence = ""
            confidence_order = {
                "exact": 0, "fuzzy": 1, "synonym": 2,
                "category": 3, "tag": 4, "weak": 5,
            }
            for prod_candidate in catalog_candidates.values():
                prod_obj = product_by_id.get(prod_candidate.product_id) if prod_candidate.product_id else None
                if not prod_obj:
                    continue
                matches, confidence = match_product_to_term(signal_key, prod_obj)
                if matches:
                    current_best = confidence_order.get(best_confidence, 99)
                    candidate_best = confidence_order.get(confidence.value, 99)
                    if candidate_best < current_best:
                        best_product = prod_candidate
                        best_confidence = confidence.value

            if best_product:
                signal_candidate.current_product = True
                signal_candidate.product_id = best_product.product_id
                signal_candidate.product_status = best_product.product_status
                signal_candidate.title = best_product.title or signal_candidate.title
                signal_candidate.sources.update(best_product.sources)
                signal_candidate.purchase_raw += best_product.purchase_raw
                signal_candidate.prices.extend(best_product.prices)
                signal_candidate.inventory_available = best_product.inventory_available
                signal_candidate.reorder_target = best_product.reorder_target
                signal_candidate.units_sold = best_product.units_sold
                signal_candidate.revenue = best_product.revenue
                signal_candidate.base_price = best_product.base_price
                signal_candidate.estimated_profit = best_product.estimated_profit
                signal_candidate.estimated_print_minutes = best_product.estimated_print_minutes
                signal_candidate.license_status = best_product.license_status
                signal_candidate.model_commercial_use_allowed = best_product.model_commercial_use_allowed
                signal_candidate.is_public = best_product.is_public
                signal_candidate.is_pos_visible = best_product.is_pos_visible
                signal_candidate.category = best_product.category
                signal_candidate.tags = best_product.tags
                signal_candidate.match_confidence = best_confidence
                signal_candidate.sell_through_rate = best_product.sell_through_rate
                signal_candidate.days_since_last_sale = best_product.days_since_last_sale
                signal_candidate.inventory_age_days = best_product.inventory_age_days
                signal_candidate.stockout_detected = best_product.stockout_detected
                signal_candidate.margin_pct = best_product.margin_pct
                signal_candidate.last_sale_at = best_product.last_sale_at

    for keyword, product_candidate in catalog_candidates.items():
        if keyword not in exact_matched_keys and keyword not in candidates:
            candidates[keyword] = product_candidate

    return candidates


def _price_resilience(candidate: OpportunityCandidate) -> int:
    if candidate.current_product and candidate.base_price > 0:
        margin = candidate.margin_pct or (candidate.estimated_profit / candidate.base_price)
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
    if candidate.stockout_detected:
        score += 8
    if candidate.margin_pct > 0.5:
        score += 6
    elif candidate.margin_pct > 0.3:
        score += 3
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

        if candidate.stockout_detected and scores["opportunity_score"] >= 50:
            return "print_now"

        if scores["opportunity_score"] >= 70 and low_inventory:
            return "print_now"
        if scores["opportunity_score"] >= 65:
            return "keep_selling"

        if candidate.sell_through_rate < 0.15 and candidate.inventory_available > 5:
            return "clearance_candidate"
        if demand < 45 and candidate.inventory_available > 0:
            return "clearance_candidate"

        if candidate.days_since_last_sale > 180 and candidate.inventory_available <= 0:
            return "retire_review"
        if demand < 35 and candidate.inventory_available <= 0:
            return "retire_review"

        return "improve_or_monitor"
    if scores["opportunity_score"] >= 65:
        return "test_product"
    if scores["opportunity_score"] >= 45:
        return "monitor"
    return "low_priority"


def _build_score_breakdown(candidate: OpportunityCandidate, scores: dict[str, int]) -> dict[str, Any]:
    return {
        "purchase_intent": {
            "raw_purchase_score": round(candidate.purchase_raw, 2),
            "units_sold": candidate.units_sold,
            "revenue": round(candidate.revenue, 2),
            "signal_total": round(candidate.signal_total, 2),
            "source_count": len(candidate.sources),
            "sources": sorted(candidate.sources),
            "sell_through_rate": candidate.sell_through_rate,
            "days_since_last_sale": candidate.days_since_last_sale,
            "stockout_detected": candidate.stockout_detected,
            "explanation": (
                f"Based on {candidate.units_sold} units sold, "
                f"${candidate.revenue:.2f} revenue, "
                f"and trend signals from {len(candidate.sources)} source(s)."
            ),
        },
        "trend_velocity": {
            "raw_velocity": round(candidate.velocity_raw, 2),
            "item_count": candidate.item_count,
            "explanation": (
                f"Velocity score based on {candidate.item_count} trend items "
                f"with raw velocity {candidate.velocity_raw:.2f}."
            ),
        },
        "price_resilience": {
            "base_price": round(candidate.base_price, 2),
            "estimated_profit": round(candidate.estimated_profit, 2),
            "avg_price": round(sum(candidate.prices) / len(candidate.prices), 2) if candidate.prices else 0,
            "margin_pct": candidate.margin_pct,
            "explanation": (
                f"Base price ${candidate.base_price:.2f}, "
                f"estimated profit ${candidate.estimated_profit:.2f}, "
                f"margin {candidate.margin_pct*100:.1f}%."
            ),
        },
        "low_saturation": {
            "trend_item_count": candidate.trend_item_count,
            "maker_signal_count": candidate.maker_signal_count,
            "source_spread": len(candidate.sources),
            "explanation": (
                f"{candidate.trend_item_count} trend items across "
                f"{candidate.maker_signal_count} maker sources."
            ),
        },
        "local_fit": {
            "matched_terms": _find_matched_local_terms(candidate.text),
            "explanation": (
                "Checked business-local terms like Clarksville, TN, teacher, military."
            ),
        },
        "production_fit": {
            "estimated_print_minutes": candidate.estimated_print_minutes,
            "estimated_profit": round(candidate.estimated_profit, 2),
            "is_public": candidate.is_public,
            "is_pos_visible": candidate.is_pos_visible,
            "inventory_available": candidate.inventory_available,
            "stockout_detected": candidate.stockout_detected,
            "explanation": (
                f"Print time {candidate.estimated_print_minutes:.0f} min, "
                f"profit ${candidate.estimated_profit:.2f}."
            ),
        },
        "license_risk": {
            "license_status": candidate.license_status,
            "model_commercial_use_allowed": candidate.model_commercial_use_allowed,
            "matched_risk_terms": _find_matched_risk_terms(candidate.text),
            "explanation": (
                f"License status: {candidate.license_status or 'unknown'}."
            ),
        },
    }


def _find_matched_local_terms(text: str) -> list[str]:
    matched = []
    for term in LOCAL_FIT_TERMS:
        if term in text.lower():
            matched.append(term)
    return matched


def _find_matched_risk_terms(text: str) -> list[str]:
    matched = []
    for term in LICENSE_RISK_TERMS:
        if term in text.lower():
            matched.append(term)
    return matched


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
        "match_confidence": candidate.match_confidence or None,
        "sell_through_rate": candidate.sell_through_rate,
        "days_since_last_sale": candidate.days_since_last_sale,
        "inventory_age_days": candidate.inventory_age_days,
        "stockout_detected": candidate.stockout_detected,
        "margin_pct": candidate.margin_pct,
        "last_sale_at": candidate.last_sale_at,
        "score_breakdown": _build_score_breakdown(candidate, scores),
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

    products: list[Product] = []
    try:
        products = (
            db_session.query(Product)
            .filter(Product.deleted_at.is_(None))
            .all()
        )
    except Exception:
        pass

    catalog_candidates = _catalog_candidates(db_session, catalog_cutoff) if products else {}
    _merge_catalog_candidates(
        candidates,
        catalog_candidates,
        products=products,
    )

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
