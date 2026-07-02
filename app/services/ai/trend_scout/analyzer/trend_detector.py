from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog import LicenseStatus
from app.models.inventory import InventoryRecord
from app.models.order import Order, OrderItem
from app.models.pos import PosSale, PosSaleItem
from app.services.trend_match import match_product_to_term
from app.services.trend_scout_weights import (
    load_buyer_source_weights as _load_buyer_weights,
    load_metric_weights as _load_metric_weights,
    load_score_weights as _load_score_weights,
    load_source_weights as _load_source_weights,
)

logger = logging.getLogger(__name__)

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

def _get_source_weights() -> dict[str, float]:
    return _load_source_weights()

def _get_metric_weights() -> dict[str, float]:
    return _load_metric_weights()

def _get_buyer_weights() -> dict[str, float]:
    return _load_buyer_weights()

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
    "snoopy",
    "peanuts",
    "hello kitty",
    "sanrio",
    "squishmallow",
    "mickey",
    "minnie",
    "mickey mouse",
    "donald duck",
    "spongebob",
    "paw patrol",
    "peppa pig",
    "super mario",
    "zelda",
    "sonic",
    "pikachu",
    "transformers",
    "lego",
    "fnaf",
    "anime",
    "naruto",
    "dragon ball",
    "ghibli",
    "coca cola",
    "nike",
    "harley davidson",
    "nfl",
    "mlb",
    "nba",
    "ncaa",
    "military branch",
    "us army",
    "us navy",
    "us air force",
    "us marines",
    "official",
    "©",
    "™",
    "®",
    "trademark",
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
    online_units_sold: int = 0
    pos_units_sold: int = 0
    admin_override: str = ""

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
                value = value[len(prefix) :].strip()
                changed = True

    return value


def _log_score(value: float, scale: float = 15.0) -> int:
    if value <= 0:
        return 0
    raw = int(round(math.log2(value + 1) * (scale / 5.0)))
    return max(0, min(100, raw))


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def _calc_signal_total(items: list[dict[str, Any]]) -> float:
    return sum(_item_signal_score(item) for item in items)


SIGNAL_METRIC_MAP = {
    "downloads": "downloads",
    "download_count": "download_count",
    "prints_count": "prints_count",
    "print_count": "print_count",
    "makes": "makes",
    "likes": "likes",
    "num_favorers": "num_favorers",
    "favorites": "favorites",
    "saves": "saves",
    "views": "views",
    "visits": "visits",
    "impressions": "impressions",
    "comments": "comments",
    "shares": "shares",
    "interest": "interest",
    "event_count": "event_count",
    "quantity": "quantity",
    "purchase_score": "purchase_score",
    "revenue": "revenue",
}


def _item_signal_score(item: dict[str, Any]) -> float:
    weights = _get_metric_weights()
    total = 0.0
    for key, weight in weights.items():
        mapped = SIGNAL_METRIC_MAP.get(key)
        if mapped and mapped in item:
            try:
                total += float(item[mapped]) * weight
            except (ValueError, TypeError):
                pass
    return total


def _item_purchase_signal(item: dict[str, Any], source: str) -> float:
    return _item_signal_score(item) * _get_buyer_weights().get(source, 0.1)


def _source_weight(source: str) -> float:
    return _get_source_weights().get(source, 1.0)


def _keyword_velocity_scores(signal_rows: list[Any]) -> dict[tuple[str, str], float]:
    weekly_counts: dict[tuple[str, str], float] = {}
    for row in signal_rows:
        items: list[dict] = row.raw_metadata.get("items", []) if row.raw_metadata else []
        week_label = _week_start(row.scraped_at).isoformat()
        item_keyword = _normalise_keyword(row.keyword_or_category)
        for item in items:
            weekly_counts[(item_keyword, week_label)] += _item_signal_score(item)
    return weekly_counts


def _collect_signal_candidates(signal_rows: list[Any]) -> dict[str, OpportunityCandidate]:
    candidates: dict[str, OpportunityCandidate] = {}
    velocity_scores = _keyword_velocity_scores(signal_rows)

    keyword_item_weeks: dict[str, set[str]] = {}
    for (keyword, week_label) in velocity_scores:
        if keyword not in keyword_item_weeks:
            keyword_item_weeks[keyword] = set()
        keyword_item_weeks[keyword].add(week_label)

    for row in signal_rows:
        keyword = _normalise_keyword(row.keyword_or_category)
        if keyword in INTERNAL_KEYWORDS:
            continue
        items = row.raw_metadata.get("items", []) if row.raw_metadata else []
        if not items:
            continue

        signal_total = _calc_signal_total(items)
        purchase_raw = sum(_item_purchase_signal(item, row.source) for item in items)
        item_count = len(items)
        source_set = {row.source}

        existing = candidates.get(keyword)
        if existing:
            existing.item_count += item_count
            existing.signal_total += signal_total
            existing.purchase_raw += purchase_raw
            existing.sources.update(source_set)
            continue

        velocity_raw = max(v for k, v in velocity_scores.items() if k[0] == keyword) if velocity_scores else 0.0

        candidates[keyword] = OpportunityCandidate(
            keyword=keyword,
            item_count=item_count,
            signal_total=signal_total,
            purchase_raw=purchase_raw,
            velocity_raw=velocity_raw,
            sources=source_set,
        )

    for keyword, candidate in candidates.items():
        candidate.maker_signal_count = (
            sum(
                1
                for row in signal_rows
                if _normalise_keyword(row.keyword_or_category) == keyword
                and row.source in MAKER_SOURCES
            )
        )
        candidate.trend_item_count = candidate.item_count
        candidate.source_count = len(candidate.sources)

    return candidates


def compute_velocity_and_momentum(db_session: Session, lookback_weeks: int = 4) -> dict[str, Any]:
    from app.models.trend import TrendSnapshot

    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    rows = (
        db_session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at >= cutoff)
        .order_by(TrendSnapshot.scraped_at.asc())
        .all()
    )

    signal_rows = [r for r in rows if r.source not in INTERNAL_KEYWORDS and not _is_error_row(r)]
    error_rows = [r for r in rows if _is_error_row(r)]
    error_map: dict[str, int] = {}
    for r in error_rows:
        error_map[r.source] = error_map.get(r.source, 0) + 1

    weekly_counts: dict[tuple[str, str], float] = {}
    source_weekly_counts: dict[tuple[str, str, str], float] = {}

    for row in signal_rows:
        items: list[dict] = row.raw_metadata.get("items", []) if row.raw_metadata else []
        week_label = _week_start(row.scraped_at).isoformat()
        item_keyword = _normalise_keyword(row.keyword_or_category)
        for item in items:
            score = _item_signal_score(item)
            weekly_counts[(item_keyword, week_label)] += score
            source_weekly_counts[(row.source, item_keyword, week_label)] = (
                source_weekly_counts.get((row.source, item_keyword, week_label), 0) + score
            )

    all_weeks_set = sorted({w for (_, w) in weekly_counts})
    keyword_week_vectors: dict[str, list[float]] = {}
    keyword_source_vectors: dict[str, dict[str, list[float]]] = {}

    for (keyword, week), count in weekly_counts.items():
        if keyword not in keyword_week_vectors:
            keyword_week_vectors[keyword] = [0.0] * len(all_weeks_set)
        try:
            idx = all_weeks_set.index(week)
            keyword_week_vectors[keyword][idx] += count
        except ValueError:
            pass

    for (source, keyword, week), count in source_weekly_counts.items():
        if keyword not in keyword_source_vectors:
            keyword_source_vectors[keyword] = {}
        if source not in keyword_source_vectors[keyword]:
            keyword_source_vectors[keyword][source] = [0.0] * len(all_weeks_set)
        try:
            idx = all_weeks_set.index(week)
            keyword_source_vectors[keyword][source][idx] += count
        except ValueError:
            pass

    keyword_mom: dict[str, dict[str, Any]] = {}
    for kw, vec in keyword_week_vectors.items():
        if len(vec) < 2:
            keyword_mom[kw] = {"velocity": 0, "direction": "flat", "total": sum(vec)}
            continue
        first_half = sum(vec[: len(vec) // 2])
        second_half = sum(vec[len(vec) // 2 :])
        velocity = second_half - first_half
        direction = "up" if velocity > 0 else ("down" if velocity < 0 else "flat")
        keyword_mom[kw] = {
            "velocity": velocity,
            "direction": direction,
            "total": sum(vec),
        }

    cross_source: dict[str, list[str]] = {}
    for kw, sv in keyword_source_vectors.items():
        present_sources = [s for s, vec in sv.items() if sum(vec) > 0]
        cross_source[kw] = present_sources

    return {
        "metadata": {
            "total_rows": len(rows),
            "signal_rows": len(signal_rows),
            "error_rows": len(error_rows),
            "lookback_weeks": lookback_weeks,
            "errors_by_source": error_map,
        },
        "keyword_momentum": keyword_mom,
        "cross_source_correlation": cross_source,
        "velocity_snapshots": all_weeks_set,
    }


def _catalog_metrics(
    db_session: Session,
) -> dict[int, dict[str, Any]]:
    from app.models import Product

    products = db_session.query(Product).all()
    product_ids = [p.id for p in products]
    if not product_ids:
        return {}

    raw_order_data = (
        db_session.query(
            OrderItem.product_id,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("total_qty"),
            func.coalesce(func.sum(OrderItem.line_total), 0.0).label("total_rev"),
            func.count(func.distinct(Order.id)).label("order_ct"),
        )
        .join(Order)
        .filter(OrderItem.product_id.in_(product_ids))
        .group_by(OrderItem.product_id)
        .all()
    )

    raw_pos_data = (
        db_session.query(
            PosSaleItem.product_id,
            func.coalesce(func.sum(PosSaleItem.quantity), 0).label("total_qty"),
            func.coalesce(func.sum(PosSaleItem.line_total), 0.0).label("total_rev"),
        )
        .join(PosSale)
        .filter(PosSaleItem.product_id.in_(product_ids))
        .group_by(PosSaleItem.product_id)
        .all()
    )

    last_sales = (
        db_session.query(
            OrderItem.product_id,
            func.max(Order.created_at).label("last_order"),
        )
        .join(Order)
        .filter(OrderItem.product_id.in_(product_ids))
        .group_by(OrderItem.product_id)
        .all()
    )

    last_pos = (
        db_session.query(
            PosSaleItem.product_id,
            func.max(PosSale.created_at).label("last_pos"),
        )
        .join(PosSale)
        .filter(PosSaleItem.product_id.in_(product_ids))
        .group_by(PosSaleItem.product_id)
        .all()
    )

    order_map: dict[int, dict[str, Any]] = {}
    for row in raw_order_data:
        order_map[row.product_id] = {
            "order_qty": int(row.total_qty),
            "order_rev": float(row.total_rev),
            "order_ct": int(row.order_ct),
        }

    for row in raw_pos_data:
        entry = order_map.setdefault(row.product_id, {"order_qty": 0, "order_rev": 0.0, "order_ct": 0})
        entry["pos_qty"] = int(row.total_qty)
        entry["pos_rev"] = float(row.total_rev)

    last_sale_map: dict[int, datetime | None] = {}
    for row in last_sales:
        last_sale_map[row.product_id] = row.last_order
    for row in last_pos:
        existing = last_sale_map.get(row.product_id)
        if row.last_pos and (existing is None or row.last_pos > existing):
            last_sale_map[row.product_id] = row.last_pos

    now = datetime.now(timezone.utc)
    metrics: dict[int, dict[str, Any]] = {}

    for p in products:
        om = order_map.get(p.id, {"order_qty": 0, "order_rev": 0.0, "order_ct": 0, "pos_qty": 0, "pos_rev": 0.0})

        order_qty = om.get("order_qty", 0)
        pos_qty = om.get("pos_qty", 0)
        total_units = order_qty + pos_qty

        total_was = (
            db_session.query(
                func.coalesce(func.sum(InventoryRecord.quantity), 0)
            )
            .filter(
                InventoryRecord.product_id == p.id,
                InventoryRecord.is_active.is_(True),
            )
            .scalar()
            or 0
        )

        sell_through = total_units / max(total_was, 1)

        last_date = last_sale_map.get(p.id)
        days_since = (now - last_date).days if last_date else 999

        inv_age = days_since if days_since < 999 else 0
        stockout = p.inventory_available is not None and int(p.inventory_available) <= 0 and total_units > 0

        margin = float(p.estimated_profit or 0) / max(float(p.base_price or 1), 0.01)

        metrics[p.id] = {
            "units_sold": total_units,
            "order_units": order_qty,
            "pos_units": pos_qty,
            "revenue": om.get("order_rev", 0.0) + om.get("pos_rev", 0.0),
            "sell_through_rate": round(sell_through, 4),
            "days_since_last_sale": days_since,
            "inventory_age_days": inv_age,
            "stockout_detected": stockout,
            "margin_pct": round(margin, 4),
            "last_sale_at": last_date.isoformat() if last_date else None,
        }

    return metrics


def _catalog_candidates(
    db_session: Session,
    catalog_metrics: dict[int, dict[str, Any]],
) -> dict[str, OpportunityCandidate]:
    from app.models import Product

    products = db_session.query(Product).all()
    candidates: dict[str, OpportunityCandidate] = {}

    for product in products:
        key = _normalise_keyword(product.name)
        m = catalog_metrics.get(product.id, {})
        candidate = OpportunityCandidate(
            keyword=key,
            title=product.name,
            current_product=True,
            product_id=product.id,
            product_status=product.status.value if product.status else "",
            sources={"catalog"},
            inventory_available=int(product.inventory_available or 0),
            reorder_target=int(product.reorder_target or 0),
            units_sold=m.get("units_sold", 0),
            online_units_sold=m.get("order_units", 0),
            pos_units_sold=m.get("pos_units", 0),
            revenue=m.get("revenue", 0.0),
            base_price=float(product.base_price or 0),
            estimated_profit=float(product.estimated_profit or 0),
            estimated_print_minutes=float(product.estimated_print_minutes or 0),
            license_status=product.license_status.value if product.license_status else "",
            model_commercial_use_allowed=bool(product.model_commercial_use_allowed),
            is_public=product.is_public,
            is_pos_visible=product.is_pos_visible,
            category=product.category.name if product.category else "",
            tags=product.tags or "",
            sell_through_rate=m.get("sell_through_rate", 0.0),
            days_since_last_sale=m.get("days_since_last_sale", 999),
            inventory_age_days=m.get("inventory_age_days", 0),
            stockout_detected=m.get("stockout_detected", False),
            margin_pct=m.get("margin_pct", 0.0),
            last_sale_at=m.get("last_sale_at"),
            admin_override=product.admin_notes or "",
        )
        candidate.prices.append(float(product.base_price or 0))
        candidates[key] = candidate

    return candidates


def _merge_catalog_candidates(
    db_session: Session,
    signal_candidates: dict[str, OpportunityCandidate],
    catalog_candidates: dict[str, OpportunityCandidate],
) -> dict[str, OpportunityCandidate]:
    from app.models import Product

    merged: dict[str, OpportunityCandidate] = dict(signal_candidates)
    products = db_session.query(Product).all() if catalog_candidates else []
    product_by_id = {p.id: p for p in products}

    for keyword, existing in catalog_candidates.items():
        if keyword in merged:
            sig = merged[keyword]
            sig.current_product = True
            sig.product_id = existing.product_id
            sig.product_status = existing.product_status
            sig.title = existing.title
            sig.sources.update(existing.sources)
            sig.item_count += existing.item_count
            sig.purchase_raw += existing.purchase_raw
            sig.prices.extend(existing.prices)
            sig.inventory_available = existing.inventory_available
            sig.reorder_target = existing.reorder_target
            sig.units_sold = existing.units_sold
            sig.revenue = existing.revenue
            sig.base_price = existing.base_price
            sig.estimated_profit = existing.estimated_profit
            sig.estimated_print_minutes = existing.estimated_print_minutes
            sig.license_status = existing.license_status
            sig.model_commercial_use_allowed = existing.model_commercial_use_allowed
            sig.is_public = existing.is_public
            sig.is_pos_visible = existing.is_pos_visible
            sig.category = existing.category
            sig.tags = existing.tags
            sig.match_confidence = "exact"
            sig.sell_through_rate = existing.sell_through_rate
            sig.days_since_last_sale = existing.days_since_last_sale
            sig.inventory_age_days = existing.inventory_age_days
            sig.stockout_detected = existing.stockout_detected
            sig.margin_pct = existing.margin_pct
            sig.last_sale_at = existing.last_sale_at
            sig.online_units_sold = existing.online_units_sold
            sig.pos_units_sold = existing.pos_units_sold
            sig.admin_override = existing.admin_override

    if products:
        for signal_key, signal_candidate in signal_candidates.items():
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
                    if confidence_order.get(confidence, 99) < current_best:
                        best_product = prod_obj
                        best_confidence = confidence

            if best_product:
                candidate = merged.setdefault(signal_key, signal_candidate)
                candidate.current_product = True
                candidate.product_id = best_product.id
                candidate.product_status = best_product.status.value if best_product.status else ""
                candidate.title = best_product.name
                candidate.match_confidence = best_confidence
                candidate.inventory_available = int(best_product.inventory_available or 0)
                candidate.reorder_target = int(best_product.reorder_target or 0)
                candidate.base_price = float(best_product.base_price or 0)
                candidate.estimated_profit = float(best_product.estimated_profit or 0)
                candidate.estimated_print_minutes = float(best_product.estimated_print_minutes or 0)
                candidate.license_status = best_product.license_status.value if best_product.license_status else ""
                candidate.model_commercial_use_allowed = bool(best_product.model_commercial_use_allowed)
                candidate.is_public = best_product.is_public
                candidate.is_pos_visible = best_product.is_pos_visible
                prod_cat_metrics = catalog_candidates.get(_normalise_keyword(best_product.name), None)
                if prod_cat_metrics:
                    candidate.sell_through_rate = prod_cat_metrics.sell_through_rate
                    candidate.days_since_last_sale = prod_cat_metrics.days_since_last_sale
                    candidate.inventory_age_days = prod_cat_metrics.inventory_age_days
                    candidate.stockout_detected = prod_cat_metrics.stockout_detected
                    candidate.margin_pct = prod_cat_metrics.margin_pct
                    candidate.last_sale_at = prod_cat_metrics.last_sale_at
                    candidate.units_sold = prod_cat_metrics.units_sold
                    candidate.revenue = prod_cat_metrics.revenue
                    candidate.online_units_sold = prod_cat_metrics.online_units_sold
                    candidate.pos_units_sold = prod_cat_metrics.pos_units_sold
                    candidate.admin_override = prod_cat_metrics.admin_override

    return merged


def _price_resilience(candidate: OpportunityCandidate) -> int:
    if candidate.base_price <= 0 and not candidate.prices:
        return 50
    avg_price = sum(candidate.prices) / len(candidate.prices) if candidate.prices else candidate.base_price
    if avg_price <= 5:
        return 72
    if avg_price <= 15:
        return 85
    if avg_price <= 30:
        return 78
    if avg_price <= 60:
        return 62
    return 50


def _low_saturation(candidate: OpportunityCandidate) -> int:
    spread = len(candidate.sources)
    if spread >= 4:
        return 30
    if spread >= 2:
        return 55
    if candidate.maker_signal_count <= 5:
        return 80
    if candidate.maker_signal_count <= 20:
        return 60
    return 40


def _local_fit(candidate: OpportunityCandidate) -> int:
    text = candidate.text
    if not text:
        return 5
    terms = _find_matched_local_terms(text)
    if not terms:
        return 5
    return min(100, max(terms.values() if isinstance(terms, dict) else [5]))


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
    if candidate.admin_override:
        override_lines = [
            line for line in candidate.admin_override.split("\n")
            if "override:license_risk" in line.lower()
        ]
        if override_lines:
            return 5

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
    if candidate.admin_override:
        override_lines = [
            line for line in candidate.admin_override.split("\n")
            if "override:recommend" in line.lower()
        ]
        for line in override_lines:
            parts = line.split(":")
            if len(parts) >= 3:
                return parts[2].strip()

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
    risk_reason = ""
    matched_risk = _find_matched_risk_terms(candidate.text)
    if candidate.license_status:
        risk_reason = f"License: {candidate.license_status}"
    elif matched_risk:
        risk_reason = f"Matched risk terms: {', '.join(matched_risk[:5])}"
    elif candidate.model_commercial_use_allowed:
        risk_reason = "Model allows commercial use"
    else:
        risk_reason = "No explicit license data"

    return {
        "purchase_intent": {
            "raw_purchase_score": round(candidate.purchase_raw, 2),
            "units_sold": candidate.units_sold,
            "online_units": candidate.online_units_sold,
            "pos_units": candidate.pos_units_sold,
            "revenue": round(candidate.revenue, 2),
            "signal_total": round(candidate.signal_total, 2),
            "source_count": len(candidate.sources),
            "sources": sorted(candidate.sources),
            "sell_through_rate": candidate.sell_through_rate,
            "days_since_last_sale": candidate.days_since_last_sale,
            "stockout_detected": candidate.stockout_detected,
            "explanation": (
                f"Based on {candidate.units_sold} units sold "
                f"({candidate.online_units_sold} online, {candidate.pos_units_sold} POS), "
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
            "risk_reason_code": risk_reason,
            "license_status": candidate.license_status,
            "model_commercial_use_allowed": candidate.model_commercial_use_allowed,
            "matched_risk_terms": matched_risk,
            "admin_override": bool(candidate.admin_override),
            "explanation": risk_reason,
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

    channel_boost = 0
    if candidate.current_product:
        online_ratio = candidate.online_units_sold / max(candidate.units_sold, 1)
        if online_ratio > 0.7:
            channel_boost = 5
        elif online_ratio < 0.3 and candidate.units_sold > 0:
            channel_boost = 8

    purchase_intent = _clamp_score(purchase_intent + channel_boost)

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

    weights = _load_score_weights()
    opportunity_score = _clamp_score(
        (scores["purchase_intent"] * weights.get("purchase_intent", 0.30))
        + (scores["trend_velocity"] * weights.get("trend_velocity", 0.18))
        + (scores["price_resilience"] * weights.get("price_resilience", 0.14))
        + (scores["low_saturation"] * weights.get("low_saturation", 0.12))
        + (scores["local_fit"] * weights.get("local_fit", 0.10))
        + (scores["production_fit"] * weights.get("production_fit", 0.12))
        - (scores["license_risk"] * weights.get("license_risk", 0.16))
    )
    scores["opportunity_score"] = opportunity_score

    action = _recommend_action(candidate, scores)
    result = {
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
        "candidate_type": "current" if candidate.current_product else "potential",
        "product_id": candidate.product_id,
        "inventory_available": candidate.inventory_available,
        "base_price": round(candidate.base_price, 2),
        "license_status": candidate.license_status or "unknown",
        "sources": sorted(candidate.sources),
        "source_count": len(candidate.sources),
        "rank": 0,
        "match_confidence": candidate.match_confidence,
        "score_breakdown": _build_score_breakdown(candidate, scores),
    }

    if hasattr(candidate, "sell_through_rate"):
        result["sell_through_rate"] = candidate.sell_through_rate
    if hasattr(candidate, "days_since_last_sale"):
        result["days_since_last_sale"] = candidate.days_since_last_sale
    if hasattr(candidate, "inventory_age_days"):
        result["inventory_age_days"] = candidate.inventory_age_days
    if hasattr(candidate, "stockout_detected"):
        result["stockout_detected"] = candidate.stockout_detected
    if hasattr(candidate, "margin_pct"):
        result["margin_pct"] = candidate.margin_pct
    if hasattr(candidate, "last_sale_at"):
        result["last_sale_at"] = candidate.last_sale_at

    return result


def compute_top_opportunities(db_session: Session, lookback_weeks: int = 4) -> list[dict[str, Any]]:
    from app.models.trend import TrendSnapshot

    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    rows = (
        db_session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at >= cutoff)
        .order_by(TrendSnapshot.scraped_at.asc())
        .all()
    )

    signal_rows = [r for r in rows if r.source not in INTERNAL_KEYWORDS and not _is_error_row(r)]

    catalog_metrics = _catalog_metrics(db_session)
    signal_candidates = _collect_signal_candidates(signal_rows)
    catalog_candidates = _catalog_candidates(db_session, catalog_metrics)
    merged = _merge_catalog_candidates(db_session, signal_candidates, catalog_candidates)

    scored = [_score_candidate(c) for c in merged.values()]
    scored.sort(key=lambda x: x["opportunity_score"], reverse=True)
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    return scored


def _is_error_row(row: Any) -> bool:
    if not row.raw_metadata:
        return False
    errors = row.raw_metadata.get("errors", [])
    return bool(errors)
