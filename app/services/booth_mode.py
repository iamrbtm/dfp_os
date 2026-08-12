from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import (
    BoothHintStatus,
    BoothModeHint,
    Expense,
    InventoryRecord,
    Market,
    PosSaleItem,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
    Product,
)
from app.services.audit import record_audit_event
from app.services.pos import get_session_summary


@dataclass(frozen=True)
class BreakEvenState:
    revenue: Decimal
    costs: Decimal
    remaining: Decimal
    profit: Decimal
    reached: bool
    elapsed_minutes: int
    sales_per_hour: Decimal
    projected_revenue: Decimal | None
    pace_warning: bool


def booth_mode_context(market_id: int | None = None, session_id: int | None = None) -> dict:
    session = _resolve_session(session_id=session_id, market_id=market_id)
    market = (
        db.session.get(Market, market_id or session.market_id)
        if (market_id or session.market_id)
        else None
    )
    summary = get_session_summary(session.id)
    break_even = calculate_break_even(session=session, market=market, summary=summary)
    hints = generate_hints(session=session, market=market, summary=summary, break_even=break_even)
    sellers = top_sellers(session.id)
    return {
        "session": session,
        "market": market,
        "summary": summary,
        "break_even": break_even,
        "hints": hints,
        "top_sellers": sellers,
    }


def calculate_break_even(
    *, session: PosSession, market: Market | None, summary: dict
) -> BreakEvenState:
    revenue = Decimal(str(summary["net_sales_total"] or 0))
    costs = _market_costs(market)
    remaining = max(Decimal("0.00"), costs - revenue)
    profit = revenue - costs
    now = datetime.now(UTC)
    opened_at = _aware(session.opened_at)
    elapsed_minutes = max(0, int((now - opened_at).total_seconds() // 60))
    hours = Decimal(str(max(elapsed_minutes, 1))) / Decimal(60)
    sales_per_hour = (revenue / hours).quantize(Decimal("0.01")) if hours > 0 else Decimal("0.00")
    projected_revenue = None
    pace_warning = False
    if market and market.end_time and market.event_date:
        close_at = datetime.combine(market.event_date, market.end_time).replace(tzinfo=UTC)
        remaining_hours = Decimal(str(max((close_at - now).total_seconds(), 0))) / Decimal(3600)
        projected_revenue = (revenue + sales_per_hour * remaining_hours).quantize(Decimal("0.01"))
        pace_warning = projected_revenue < costs
    return BreakEvenState(
        revenue=revenue,
        costs=costs,
        remaining=remaining,
        profit=profit,
        reached=remaining <= 0,
        elapsed_minutes=elapsed_minutes,
        sales_per_hour=sales_per_hour,
        projected_revenue=projected_revenue,
        pace_warning=pace_warning,
    )


def generate_hints(
    *, session: PosSession, market: Market | None, summary: dict, break_even: BreakEvenState
) -> list[BoothModeHint]:
    candidates = []
    if break_even.pace_warning:
        candidates.append(
            {
                "key": "pace_break_even",
                "title": "Sales pace is behind break-even",
                "message": "Push simple impulse items or bundles before the next lull.",
                "severity": "warning",
            }
        )
    # Approaching break-even (within 20%) — celebratory nudge
    if (
        not break_even.reached
        and break_even.costs > 0
        and break_even.remaining < break_even.costs * Decimal("0.20")
    ):
        candidates.append(
            {
                "key": "approaching_break_even",
                "title": "Almost there — break-even is close!",
                "message": (
                    f"Only ${break_even.remaining:.2f} to go. Keep the momentum and "
                    "you'll be profitable soon."
                ),
                "severity": "info",
            }
        )
    slow_high_margin = _slow_high_margin_product(session)
    if slow_high_margin:
        candidates.append(
            {
                "key": f"push_margin_{slow_high_margin.id}",
                "title": f"Push {slow_high_margin.name}",
                "message": "This item has strong margin but has not sold in this session yet.",
                "severity": "info",
            }
        )
    # Top performer restock hint
    top = _top_selling_product(session)
    if top:
        low_record = (
            InventoryRecord.query.filter(
                InventoryRecord.product_id == top.id,
                session.inventory_location_id is not None,
                InventoryRecord.location_id == session.inventory_location_id,
                InventoryRecord.quantity_on_hand <= InventoryRecord.reorder_threshold,
            ).first()
            if session.inventory_location_id
            else None
        )
        if low_record:
            candidates.append(
                {
                    "key": f"top_performer_restock_{top.id}",
                    "title": f"Restock {top.name} — your #1 seller is running low",
                    "message": (
                        f"Only {low_record.quantity_on_hand} left in market bin. "
                        "Refill now before the rush."
                    ),
                    "severity": "warning",
                }
            )
    low_stock = _low_market_stock(session)
    if low_stock:
        candidates.append(
            {
                "key": f"low_stock_{low_stock.id}",
                "title": f"Refill {low_stock.name}",
                "message": "Market-bin stock is low. Refill the tray before checkout gets busy.",
                "severity": "warning",
            }
        )
    if summary["sale_count"] == 0:
        candidates.append(
            {
                "key": "first_sale",
                "title": "No sales yet",
                "message": "Check table visibility, price tags, and impulse tray placement.",
                "severity": "info",
            }
        )
    # Slow session at midpoint
    if market and market.start_time and market.end_time and market.event_date:
        now = datetime.now(UTC)
        start_at = datetime.combine(market.event_date, market.start_time).replace(tzinfo=UTC)
        close_at = datetime.combine(market.event_date, market.end_time).replace(tzinfo=UTC)
        total_duration = (close_at - start_at).total_seconds()
        elapsed = (now - start_at).total_seconds()
        if total_duration > 0 and elapsed >= total_duration * 0.5 and summary["sale_count"] == 0:
            candidates.append(
                {
                    "key": "slow_session_midpoint",
                    "title": "Halfway through with no sales",
                    "message": (
                        "You're at the halfway point with zero sales. Try repositioning "
                        "impulse items to the front of the table."
                    ),
                    "severity": "warning",
                }
            )
    # Heavy cash payment mix hint
    revenue = break_even.revenue
    if revenue > 0:
        cash_total = summary.get("cash_sales_total", Decimal(0))
        if Decimal(str(cash_total)) / revenue > Decimal("0.80"):
            candidates.append(
                {
                    "key": "payment_mix_heavy_cash",
                    "title": "Most payments are cash",
                    "message": (
                        "Over 80% of revenue is cash. Point customers to Venmo, "
                        "Cash App, or card to simplify end-of-day counting."
                    ),
                    "severity": "info",
                }
            )
    return [
        _upsert_hint(session, market, candidate)
        for candidate in candidates
        if not _suppressed(session, candidate["key"])
    ]


def update_hint_status(
    hint: BoothModeHint, status: BoothHintStatus, *, actor_id: int | None = None
) -> BoothModeHint:
    before = {"status": hint.status.value}
    hint.status = status
    hint.acted_at = datetime.now(UTC)
    if status == BoothHintStatus.SNOOZED:
        snooze_minutes = int(current_app.config.get("BOOTH_MODE_SNOOZE_MINUTES", 30))
        hint.snoozed_until = datetime.now(UTC) + timedelta(minutes=snooze_minutes)
    db.session.add(hint)
    db.session.commit()
    record_audit_event(
        action=f"booth_hint.{status.value}",
        entity_type="booth_mode_hint",
        entity_id=hint.id,
        before_state=before,
        after_state={"status": hint.status.value, "key": hint.key},
        source_module=__name__,
        actor_id=actor_id,
    )
    return hint


def top_sellers(session_id: int, limit: int = 8) -> list[dict]:
    """Return the top-selling products for a POS session, ordered by qty sold."""
    rows = (
        db.session.query(
            PosSaleItem.product_id,
            func.sum(PosSaleItem.quantity).label("qty_sold"),
            func.sum(PosSaleItem.line_total).label("revenue"),
        )
        .join(PosSaleItem.sale)
        .filter(
            PosSaleItem.product_id.is_not(None),
            PosSaleItem.sale.has(pos_session_id=session_id, status=PosSaleStatus.COMPLETED),
        )
        .group_by(PosSaleItem.product_id)
        .order_by(func.sum(PosSaleItem.quantity).desc())
        .limit(limit)
        .all()
    )
    results = []
    for product_id, qty_sold, revenue in rows:
        product = db.session.get(Product, product_id)
        if product is None:
            continue
        results.append(
            {
                "product": product,
                "qty_sold": int(qty_sold),
                "revenue": Decimal(str(revenue or 0)),
                "estimated_profit": product.estimated_profit,
            }
        )
    return results


def _resolve_session(*, session_id: int | None, market_id: int | None) -> PosSession:
    query = PosSession.query.filter_by(status=PosSessionStatus.OPEN)
    if session_id:
        session = db.session.get(PosSession, session_id)
    elif market_id:
        session = query.filter_by(market_id=market_id).order_by(PosSession.id.desc()).first()
    else:
        session = query.order_by(PosSession.id.desc()).first()
    if session is None:
        raise ValueError("No open POS session found for Booth Mode.")
    return session


def _market_costs(market: Market | None) -> Decimal:
    if market is None:
        return Decimal("0.00")
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.related_market_id == market.id)
        .scalar()
    )
    return Decimal(str(market.total_booth_cost or 0)) + Decimal(str(expenses or 0))


def _slow_high_margin_product(session: PosSession) -> Product | None:
    sold_ids = {
        product_id
        for (product_id,) in db.session.query(PosSaleItem.product_id)
        .join(PosSaleItem.sale)
        .filter(
            PosSaleItem.product_id.is_not(None), PosSaleItem.sale.has(pos_session_id=session.id)
        )
        .all()
    }
    query = Product.query.filter(Product.is_pos_visible.is_(True), Product.estimated_profit > 0)
    if sold_ids:
        query = query.filter(Product.id.not_in(sold_ids))
    return query.order_by(Product.estimated_profit.desc()).first()


def _top_selling_product(session: PosSession) -> Product | None:
    """Return the product with the most units sold in the current session."""
    row = (
        db.session.query(
            PosSaleItem.product_id,
            func.sum(PosSaleItem.quantity).label("qty"),
        )
        .join(PosSaleItem.sale)
        .filter(
            PosSaleItem.product_id.is_not(None),
            PosSaleItem.sale.has(pos_session_id=session.id, status=PosSaleStatus.COMPLETED),
        )
        .group_by(PosSaleItem.product_id)
        .order_by(func.sum(PosSaleItem.quantity).desc())
        .first()
    )
    if row is None:
        return None
    return db.session.get(Product, row[0])


def _low_market_stock(session: PosSession) -> Product | None:
    if not session.inventory_location_id:
        return None
    record = (
        InventoryRecord.query.filter(
            InventoryRecord.location_id == session.inventory_location_id,
            InventoryRecord.quantity_on_hand <= InventoryRecord.reorder_threshold,
        )
        .order_by(InventoryRecord.quantity_on_hand.asc())
        .first()
    )
    return record.product if record else None


def _upsert_hint(session: PosSession, market: Market | None, candidate: dict) -> BoothModeHint:
    hint = BoothModeHint.query.filter_by(
        pos_session_id=session.id,
        key=candidate["key"],
    ).first()
    if hint is None:
        hint = BoothModeHint(pos_session=session, market=market, **candidate)
        db.session.add(hint)
    else:
        hint.title = candidate["title"]
        hint.message = candidate["message"]
        hint.severity = candidate["severity"]
        if (
            hint.status == BoothHintStatus.SNOOZED
            and hint.snoozed_until
            and _aware(hint.snoozed_until) <= datetime.now(UTC)
        ):
            hint.status = BoothHintStatus.OPEN
            hint.snoozed_until = None
    db.session.commit()
    return hint


def _suppressed(session: PosSession, key: str) -> bool:
    hint = BoothModeHint.query.filter_by(pos_session_id=session.id, key=key).first()
    if hint is None:
        return False
    if hint.status in {BoothHintStatus.DISMISSED, BoothHintStatus.ACCEPTED}:
        return True
    return (
        hint.status == BoothHintStatus.SNOOZED
        and hint.snoozed_until is not None
        and _aware(hint.snoozed_until) > datetime.now(UTC)
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
