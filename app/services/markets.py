from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import Market, MarketStatus, Expense, Order, PosSale, PosSession, PosSessionStatus


def get_market_performance(market: Market) -> dict:
    total_sales = _get_market_sales_total(market)
    total_expenses = _get_market_expenses_total(market)
    booth_cost = (market.booth_fee or Decimal(0)) + (market.application_fee or Decimal(0))

    return {
        "market": market,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "booth_cost": booth_cost,
        "estimated_profit": total_sales - total_expenses - booth_cost,
        "booth_fee_pct": _calc_pct(booth_cost, total_sales),
        "top_products": _get_top_products(market),
        "payment_methods": _get_payment_methods(market),
        "units_sold": _get_units_sold(market),
    }


def _get_market_sales_total(market: Market) -> Decimal:
    result = db.session.query(func.sum(Order.total)).filter(
        Order.market_id == market.id,
        Order.deleted_at.is_(None),
    ).scalar()
    return result or Decimal(0)


def _get_market_expenses_total(market: Market) -> Decimal:
    result = db.session.query(func.sum(Expense.amount)).filter(
        Expense.related_market_id == market.id
    ).scalar()
    return result or Decimal(0)


def _get_top_products(market: Market, limit: int = 5) -> list[dict]:
    from app.models import PosSaleItem, PosSaleItemType
    results = (
        db.session.query(
            PosSaleItem.description,
            func.sum(PosSaleItem.quantity).label("total_qty"),
            func.sum(PosSaleItem.line_total).label("total_revenue"),
        )
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market.id,
            PosSession.status != PosSessionStatus.VOIDED,
            PosSaleItem.item_type == PosSaleItemType.PRODUCT,
        )
        .group_by(PosSaleItem.description)
        .order_by(func.sum(PosSaleItem.line_total).desc())
        .limit(limit)
        .all()
    )
    return [
        {"name": r[0], "quantity": int(r[1]), "revenue": Decimal(str(r[2])) if r[2] else Decimal(0)}
        for r in results
    ]


def _get_payment_methods(market: Market) -> list[dict]:
    results = (
        db.session.query(
            PosSale.payment_method,
            func.count(PosSale.id).label("count"),
            func.sum(PosSale.total).label("total"),
        )
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market.id,
            PosSession.status != PosSessionStatus.VOIDED,
        )
        .group_by(PosSale.payment_method)
        .all()
    )
    return [
        {"method": r[0] or "unknown", "count": int(r[1]), "total": Decimal(str(r[2])) if r[2] else Decimal(0)}
        for r in results
    ]


def _get_units_sold(market: Market) -> int:
    from app.models import PosSaleItem, PosSaleItemType
    result = db.session.query(func.sum(PosSaleItem.quantity)).join(
        PosSale, PosSale.id == PosSaleItem.pos_sale_id
    ).join(
        PosSession, PosSession.id == PosSale.pos_session_id
    ).filter(
        PosSession.market_id == market.id,
        PosSession.status != PosSessionStatus.VOIDED,
        PosSaleItem.item_type == PosSaleItemType.PRODUCT,
    ).scalar()
    return int(result or 0)


def _calc_pct(part: Decimal, total: Decimal) -> float | None:
    if total and total > 0:
        return float(part / total * 100)
    return None


def get_upcoming_markets(limit: int = 5) -> list[Market]:
    return Market.query.filter(
        Market.status.in_([MarketStatus.SCHEDULED])
    ).order_by(Market.event_date.asc()).limit(limit).all()
