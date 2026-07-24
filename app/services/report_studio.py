from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from flask import url_for
from sqlalchemy import func, select

from app.extensions import db
from app.models import Market, MarketStatus


REPORT_CATEGORIES = {
    "Markets": [
        {
            "key": "vendor-market-heat-map",
            "title": "Vendor Market Heat Map",
            "description": "Map markets by profit, distance, booth fee, weather risk, traffic, and repeat quality. Helps decide where to apply next.",
            "endpoint": "report_studio.heat_map",
            "export_csv": True,
        },
        {
            "key": "market-application-tracker",
            "title": "Market Application Tracker",
            "description": "Pipeline view of market applications: deadlines, costs, status counts, and follow-up needs.",
            "endpoint": "report_studio.application_tracker",
            "export_csv": True,
        },
    ],
    "Products": [
        {
            "key": "product-readiness",
            "title": "Product Readiness",
            "description": "Products missing photos, cost data, descriptions, or license verification.",
            "endpoint": None,
            "export_csv": False,
        },
        {
            "key": "dead-stock",
            "title": "Dead Stock Rescue",
            "description": "Inventory sitting too long with suggested actions.",
            "endpoint": None,
            "export_csv": False,
        },
    ],
    "Inventory": [
        {
            "key": "low-stock",
            "title": "Low Stock Alerts",
            "description": "Inventory items approaching reorder thresholds.",
            "endpoint": None,
            "export_csv": False,
        },
    ],
    "POS": [
        {
            "key": "pos-summary",
            "title": "POS Sales Summary",
            "description": "Revenue, payment methods, and units sold across POS sessions.",
            "endpoint": None,
            "export_csv": False,
        },
    ],
    "Orders": [
        {
            "key": "order-fulfillment",
            "title": "Order Fulfillment",
            "description": "Open orders, pickup schedules, and completion status.",
            "endpoint": None,
            "export_csv": False,
        },
    ],
    "Printers": [
        {
            "key": "printer-reliability",
            "title": "Printer Reliability",
            "description": "Failure rates, common causes, and printer productivity.",
            "endpoint": "report_studio.printer_reliability",
            "export_csv": False,
        },
    ],
    "Promotion": [
        {
            "key": "content-pipeline",
            "title": "Content Pipeline",
            "description": "Content drafts, approvals, and publishing status.",
            "endpoint": None,
            "export_csv": False,
        },
    ],
}


def get_report_catalog() -> list[dict[str, Any]]:
    catalog = []
    for category, reports in REPORT_CATEGORIES.items():
        for report in reports:
            entry = dict(report)
            entry["category"] = category
            if report.get("endpoint"):
                entry["url"] = url_for(report["endpoint"])
            else:
                entry["url"] = None
            entry["last_updated"] = None
            catalog.append(entry)
    return catalog


def get_data_quality_summary() -> dict[str, Any]:
    warnings: list[dict[str, str]] = []

    total_markets = db.session.query(func.count(Market.id)).scalar() or 0
    completed_markets = (
        db.session.query(func.count(Market.id))
        .filter(Market.status == MarketStatus.COMPLETED)
        .scalar()
        or 0
    )
    markets_with_coords = (
        db.session.query(func.count(Market.id))
        .filter(Market.latitude.isnot(None), Market.longitude.isnot(None))
        .scalar()
        or 0
    )

    if total_markets == 0:
        warnings.append({"type": "warning", "message": "No markets created yet. Add markets to enable market reports."})
    elif completed_markets == 0:
        warnings.append(
            {"type": "info", "message": "No completed markets yet. Market profitability reports will populate after the first market is completed."}
        )

    if markets_with_coords < total_markets:
        missing = total_markets - markets_with_coords
        warnings.append(
            {
                "type": "warning",
                "message": f"{missing} market(s) missing geographic coordinates. The heat map will show these in a table view until coordinates are added.",
            }
        )

    from app.models import Product

    db.session.query(func.count(Product.id)).scalar() or 0
    products_no_price = (
        db.session.query(func.count(Product.id))
        .filter((Product.base_price.is_(None)) | (Product.base_price == 0))
        .scalar()
        or 0
    )
    if products_no_price > 0:
        warnings.append(
            {
                "type": "warning",
                "message": f"{products_no_price} product(s) missing a base price. Cost and margin calculations may be incomplete.",
            }
        )

    return {"warnings": warnings, "total_markets": total_markets, "completed_markets": completed_markets}


def get_vendor_market_heat_map(params: dict[str, str]) -> list[dict[str, Any]]:
    stmt = select(Market).order_by(Market.event_date.is_(None), Market.event_date.desc())

    status_filter = params.get("status", "").strip()
    if status_filter:
        stmt = stmt.where(Market.status == status_filter)

    location = params.get("location", "").strip()
    if location:
        parts = [p.strip() for p in location.split(",")]
        city_part = parts[0] if parts else ""
        state_part = parts[1] if len(parts) > 1 else ""
        if city_part:
            stmt = stmt.where(Market.city.ilike(f"%{city_part}%"))
        if state_part:
            stmt = stmt.where(Market.state.ilike(f"%{state_part}%"))

    date_from = params.get("date_from", "").strip()
    if date_from:
        try:
            from_date = date.fromisoformat(date_from)
            stmt = stmt.where(Market.event_date >= from_date)
        except (ValueError, TypeError):
            pass

    date_to = params.get("date_to", "").strip()
    if date_to:
        try:
            to_date = date.fromisoformat(date_to)
            stmt = stmt.where(Market.event_date <= to_date)
        except (ValueError, TypeError):
            pass

    min_profit_str = params.get("min_profit", "").strip()
    min_profit = None
    if min_profit_str:
        try:
            min_profit = Decimal(min_profit_str)
        except (ValueError, ArithmeticError):
            min_profit = None

    results = db.session.execute(stmt).scalars().all()

    data = []
    for market in results:
        profit = market.calculated_profit
        if min_profit is not None and profit < min_profit:
            continue

        revenue = market.calculated_revenue
        margin_pct = market.profit_margin_pct

        data.append(
            {
                "id": market.id,
                "name": market.name,
                "city": market.city,
                "state": market.state,
                "status": market.status.value if market.status else None,
                "event_date": market.event_date.isoformat() if market.event_date else None,
                "latitude": market.latitude,
                "longitude": market.longitude,
                "booth_fee": float(market.booth_fee) if market.booth_fee else 0,
                "revenue": float(revenue),
                "profit": float(profit),
                "margin_pct": float(margin_pct) if margin_pct else None,
                "worth_repeating": market.worth_repeating,
                "has_coordinates": market.latitude is not None and market.longitude is not None,
                "notes": market.notes,
            }
        )

    return data


def get_market_application_pipeline_report(params: dict[str, str]) -> dict[str, Any]:
    application_statuses = [
        MarketStatus.INTERESTED,
        MarketStatus.APPLIED,
        MarketStatus.ACCEPTED,
        MarketStatus.WAITLISTED,
        MarketStatus.REJECTED,
    ]

    stmt = (
        select(Market)
        .where(Market.status.in_(application_statuses))
        .order_by(Market.application_deadline.is_(None), Market.application_deadline.asc())
    )

    markets = db.session.execute(stmt).scalars().all()

    status_counts: dict[str, int] = {}
    for s in application_statuses:
        status_counts[s.value] = 0
    for m in markets:
        status_counts[m.status.value] = status_counts.get(m.status.value, 0) + 1

    now = date.today()
    upcoming_deadlines = [m for m in markets if m.application_deadline and m.application_deadline >= now]
    fees_at_risk = sum((m.application_fee or Decimal(0)) + (m.booth_fee or Decimal(0)) for m in markets if m.status in (MarketStatus.INTERESTED, MarketStatus.APPLIED))

    missing_docs = [m for m in markets if not m.required_documents or m.required_documents.strip() == ""]

    needs_follow_up = [m for m in markets if m.follow_up_date and m.follow_up_date <= now]

    pipeline_data = []
    for m in markets:
        pipeline_data.append(
            {
                "id": m.id,
                "name": m.name,
                "city": m.city,
                "state": m.state,
                "status": m.status.value if m.status else None,
                "application_deadline": m.application_deadline.isoformat() if m.application_deadline else None,
                "application_fee": float(m.application_fee) if m.application_fee else 0,
                "booth_fee": float(m.booth_fee) if m.booth_fee else 0,
                "total_fee": float((m.application_fee or Decimal(0)) + (m.booth_fee or Decimal(0))),
                "has_documents": bool(m.required_documents and m.required_documents.strip()),
                "follow_up_date": m.follow_up_date.isoformat() if m.follow_up_date else None,
                "needs_follow_up": m.follow_up_date is not None and m.follow_up_date <= now,
                "worth_repeating": m.worth_repeating,
                "notes": m.notes,
                "application_url": m.application_url,
                "application_contact": m.application_contact,
            }
        )

    return {
        "pipeline": pipeline_data,
        "status_counts": status_counts,
        "upcoming_deadlines": len(upcoming_deadlines),
        "fees_at_risk": float(fees_at_risk),
        "missing_documents_count": len(missing_docs),
        "needs_follow_up_count": len(needs_follow_up),
        "total_applications": len(markets),
    }


def get_printer_reliability_report() -> dict[str, Any]:
    from app.services.printer_reliability import get_reliability_report_rows
    rows = get_reliability_report_rows()
    highest_risk = sorted(rows, key=lambda row: (row["failure_rate"], row["failed_count"]), reverse=True)
    return {
        "printers": rows,
        "printer_count": len(rows),
        "failed_count": sum(int(row["failed_count"]) for row in rows),
        "completed_count": sum(int(row["completed_count"]) for row in rows),
        "highest_risk": highest_risk[:3],
    }
