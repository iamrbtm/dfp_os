from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    BoothHintStatus,
    BoothModeHint,
    Expense,
    InventoryRecord,
    Market,
    PosSaleItem,
    PosSaleItemType,
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
    market = db.session.get(Market, market_id or session.market_id) if (market_id or session.market_id) else None
    summary = get_session_summary(session.id)
    break_even = calculate_break_even(session=session, market=market, summary=summary)
    hints = generate_hints(session=session, market=market, summary=summary, break_even=break_even)
    return {
        "session": session,
        "market": market,
        "summary": summary,
        "break_even": break_even,
        "hints": hints,
    }


def calculate_break_even(*, session: PosSession, market: Market | None, summary: dict) -> BreakEvenState:
    revenue = Decimal(str(summary["net_sales_total"] or 0))
    costs = _market_costs(market)
    remaining = max(Decimal("0.00"), costs - revenue)
    profit = revenue - costs
    now = datetime.now(timezone.utc)
    opened_at = _aware(session.opened_at)
    elapsed_minutes = max(0, int((now - opened_at).total_seconds() // 60))
    hours = Decimal(str(max(elapsed_minutes, 1))) / Decimal("60")
    sales_per_hour = (revenue / hours).quantize(Decimal("0.01")) if hours > 0 else Decimal("0.00")
    projected_revenue = None
    pace_warning = False
    if market and market.end_time and market.event_date:
        close_at = datetime.combine(market.event_date, market.end_time).replace(tzinfo=timezone.utc)
        remaining_hours = Decimal(str(max((close_at - now).total_seconds(), 0))) / Decimal("3600")
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


def generate_hints(*, session: PosSession, market: Market | None, summary: dict, break_even: BreakEvenState) -> list[BoothModeHint]:
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
    return [_upsert_hint(session, market, candidate) for candidate in candidates if not _suppressed(session, candidate["key"])]


def update_hint_status(hint: BoothModeHint, status: BoothHintStatus, *, actor_id: int | None = None) -> BoothModeHint:
    before = {"status": hint.status.value}
    hint.status = status
    hint.acted_at = datetime.now(timezone.utc)
    if status == BoothHintStatus.SNOOZED:
        hint.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=30)
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
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.related_market_id == market.id).scalar()
    return Decimal(str(market.total_booth_cost or 0)) + Decimal(str(expenses or 0))


def _slow_high_margin_product(session: PosSession) -> Product | None:
    sold_ids = {
        product_id
        for (product_id,) in db.session.query(PosSaleItem.product_id)
        .join(PosSaleItem.sale)
        .filter(PosSaleItem.product_id.is_not(None), PosSaleItem.sale.has(pos_session_id=session.id))
        .all()
    }
    query = Product.query.filter(Product.is_pos_visible.is_(True), Product.estimated_profit > 0)
    if sold_ids:
        query = query.filter(Product.id.not_in(sold_ids))
    return query.order_by(Product.estimated_profit.desc()).first()


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
        if hint.status == BoothHintStatus.SNOOZED and hint.snoozed_until and _aware(hint.snoozed_until) <= datetime.now(timezone.utc):
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
    if hint.status == BoothHintStatus.SNOOZED and hint.snoozed_until and _aware(hint.snoozed_until) > datetime.now(timezone.utc):
        return True
    return False


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
