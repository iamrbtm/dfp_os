from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Market,
    MarketPackingList,
    MarketStatus,
    MarketTableLayout,
    MarketTablePlacement,
    MarketTableSection,
    PosSale,
    PosSaleItem,
    PosSaleItemType,
    PosSession,
    PosSessionStatus,
    Product,
    TableSectionType,
)
from app.services.markets import record_market_audit


def get_impulse_tray_products(market_id: int | None = None) -> list[dict]:
    """Get all products currently (or previously) placed in impulse tray sections,
    with historical sell-through data."""
    query = (
        db.session.query(
            MarketTablePlacement,
            MarketTableSection,
            MarketTableLayout,
            Market,
        )
        .join(MarketTableSection, MarketTablePlacement.section_id == MarketTableSection.id)
        .join(MarketTableLayout, MarketTableSection.layout_id == MarketTableLayout.id)
        .join(Market, MarketTableLayout.market_id == Market.id)
        .filter(MarketTableSection.section_type == TableSectionType.IMPULSE_TRAY)
    )
    if market_id:
        query = query.filter(MarketTableLayout.market_id == market_id)

    rows = query.order_by(MarketTableLayout.created_at.desc(), MarketTableSection.sort_order).all()
    results: list[dict] = []
    for placement, section, layout, market in rows:
        sell_through = _calc_sell_through(market.id, placement.product_id)
        results.append({
            "placement": placement,
            "section": section,
            "layout": layout,
            "market": market,
            "product": placement.product,
            "sell_through_qty": sell_through["sold"],
            "sell_through_revenue": sell_through["revenue"],
            "sell_through_rate": sell_through["rate"],
        })
    return results


def get_impulse_tray_recommendations(market_id: int | None = None) -> dict:
    """Analyze impulse tray performance and generate rotation suggestions."""
    placements = get_impulse_tray_products(market_id)

    if not placements:
        return {
            "placements": [],
            "top_performers": [],
            "bottom_performers": [],
            "recommendations": [],
            "total_products": 0,
            "total_revenue": Decimal("0.00"),
        }

    total_revenue = sum((p["sell_through_revenue"] or Decimal("0")) for p in placements)
    total_sold = sum((p["sell_through_qty"] or 0) for p in placements)

    sorted_by_revenue = sorted(placements, key=lambda p: p["sell_through_revenue"] or Decimal("0"), reverse=True)
    top_performers = sorted_by_revenue[:5]
    bottom_performers = sorted_by_revenue[-5:] if len(sorted_by_revenue) >= 5 else sorted_by_revenue

    recommendations = []
    if bottom_performers:
        for p in bottom_performers:
            if p["product"]:
                qty = p.get("placement", {}).get("quantity")
                if hasattr(p["placement"], "quantity"):
                    qty = p["placement"].quantity
                recommendations.append({
                    "type": "rotate_out",
                    "product_name": p["product"].name,
                    "product_id": p["product"].id,
                    "reason": f"Low impulse sell-through (${float(p['sell_through_revenue'] or 0):.2f} in {p.get('sell_through_qty', 0)} units)",
                    "suggested_replacement": None,
                })

    names_in_impulse = {p["product"].name for p in placements if p["product"]}
    high_performers = (
        db.session.query(
            Product,
            func.sum(PosSaleItem.quantity).label("total_qty"),
            func.sum(PosSaleItem.line_total).label("total_revenue"),
        )
        .join(PosSaleItem, PosSaleItem.product_id == Product.id)
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.status != PosSessionStatus.VOIDED,
            PosSaleItem.item_type == PosSaleItemType.PRODUCT,
            ~Product.name.in_(names_in_impulse) if names_in_impulse else True,
            Product.is_active == True,
            Product.is_pos_visible == True,
        )
        .group_by(Product.id, Product.name, Product.base_price)
        .order_by(func.sum(PosSaleItem.line_total).desc())
        .limit(5)
        .all()
    )

    for product, qty, revenue in high_performers:
        if len(recommendations) >= len(bottom_performers):
            break
        recommendations.append({
            "type": "rotate_in",
            "product_name": product.name,
            "product_id": product.id,
            "reason": f"Strong seller not yet in impulse tray (${float(revenue):.2f} in {int(qty)} units)",
            "suggested_replacement": None,
        })

    return {
        "placements": placements,
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
        "recommendations": recommendations,
        "total_products": len(placements),
        "total_revenue": total_revenue,
        "total_sold": total_sold,
    }


def _calc_sell_through(market_id: int, product_id: int) -> dict:
    sold = (
        db.session.query(func.coalesce(func.sum(PosSaleItem.quantity), 0))
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market_id,
            PosSession.status != PosSessionStatus.VOIDED,
            PosSaleItem.product_id == product_id,
            PosSaleItem.item_type == PosSaleItemType.PRODUCT,
        )
        .scalar()
    ) or 0

    revenue = (
        db.session.query(func.coalesce(func.sum(PosSaleItem.line_total), 0))
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market_id,
            PosSession.status != PosSessionStatus.VOIDED,
            PosSaleItem.product_id == product_id,
            PosSaleItem.item_type == PosSaleItemType.PRODUCT,
        )
        .scalar()
    ) or Decimal("0.00")

    packed = (
        db.session.query(func.coalesce(func.sum(MarketPackingList.packed_quantity), 0))
        .filter(
            MarketPackingList.market_id == market_id,
            MarketPackingList.product_id == product_id,
        )
        .scalar()
    ) or 0

    rate = round(int(sold) / int(packed) * 100, 1) if int(packed) > 0 else None

    return {
        "sold": int(sold),
        "revenue": Decimal(str(revenue)) if isinstance(revenue, (int, float)) else revenue,
        "packed": int(packed),
        "rate": rate,
    }


def optimize_impulse_tray(
    market_id: int,
    *,
    max_slots: int = 6,
    actor=None,
) -> list[dict]:
    """Generate optimized impulse tray product suggestions for a market
    based on historical impulse sell-through data."""
    layout = (
        MarketTableLayout.query
        .filter_by(market_id=market_id)
        .order_by(MarketTableLayout.created_at.desc())
        .first()
    )
    if layout:
        impulse_section = MarketTableSection.query.filter_by(
            layout_id=layout.id, section_type=TableSectionType.IMPULSE_TRAY
        ).first()
    else:
        impulse_section = None

    recommendations = get_impulse_tray_recommendations()
    suggestions = []

    for rec in recommendations.get("recommendations", []):
        if rec["type"] == "rotate_in" and len(suggestions) < max_slots:
            suggestions.append(rec["product_name"])

    record_market_audit(
        "impulse_tray.optimized",
        "market",
        market_id,
        actor=actor,
        after_state={
            "suggestions": suggestions,
            "max_slots": max_slots,
            "total_recommendations": len(recommendations.get("recommendations", [])),
        },
    )
    return suggestions
