from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import func

from app.extensions import db
from app.models import (
    Expense,
    Market,
    MarketStatus,
    Order,
    OrderItem,
    OrderStatus,
    PosSale,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
    PrintJob,
    PrintJobStatus,
    Printer,
    Product,
    ProductVariant,
)


def executive_summary() -> dict:
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    today_revenue = (
        db.session.query(func.sum(Order.total))
        .filter(
            func.date(Order.completed_at) == today,
            Order.deleted_at.is_(None),
        )
        .scalar() or Decimal(0)
    )

    month_revenue = (
        db.session.query(func.sum(Order.total))
        .filter(
            func.date(Order.completed_at) >= month_start,
            Order.deleted_at.is_(None),
        )
        .scalar() or Decimal(0)
    )

    open_orders_count = Order.query.filter(
        Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PRINTING]),
        Order.deleted_at.is_(None),
    ).count()

    from app.models import CustomRequest, CustomRequestStatus
    custom_count = CustomRequest.query.filter(
        ~CustomRequest.status.in_([CustomRequestStatus.COMPLETED, CustomRequestStatus.CANCELLED, CustomRequestStatus.ARCHIVED])
    ).count()

    print_jobs_queued = PrintJob.query.filter(
        PrintJob.status.in_([PrintJobStatus.QUEUED])
    ).count()

    from app.models import InventoryRecord
    low_inv = InventoryRecord.query.filter(
        InventoryRecord.quantity_on_hand <= InventoryRecord.reorder_threshold,
        InventoryRecord.reorder_threshold > 0,
    ).count()

    from app.models import FilamentSpool, FilamentStatus
    low_filament = FilamentSpool.query.filter(
        FilamentSpool.status == FilamentStatus.LOW
    ).count()

    upcoming_markets = Market.query.filter(
        Market.status.in_([MarketStatus.SCHEDULED, MarketStatus.ACCEPTED])
    ).order_by(Market.event_date.asc()).limit(5).all()

    month_pos = (
        db.session.query(func.sum(PosSale.total))
        .filter(
            func.date(PosSale.created_at) >= month_start,
            PosSale.status == PosSaleStatus.COMPLETED,
        )
        .scalar() or Decimal(0)
    )

    month_expenses = (
        db.session.query(func.sum(Expense.amount))
        .filter(func.date(Expense.date) >= month_start)
        .scalar() or Decimal(0)
    )

    paid_requests = (
        db.session.query(func.count(CustomRequest.id))
        .filter(
            CustomRequest.status.in_([CustomRequestStatus.COMPLETED]),
            CustomRequest.amount_paid.isnot(None),
            CustomRequest.total.isnot(None),
            CustomRequest.amount_paid >= CustomRequest.total,
        )
        .scalar() or 0
    )

    return {
        "today_revenue": today_revenue,
        "month_revenue": month_revenue,
        "month_pos_revenue": month_pos,
        "month_expenses": month_expenses,
        "estimated_month_profit": month_revenue - month_expenses,
        "open_orders_count": open_orders_count,
        "open_custom_requests": custom_count,
        "custom_requests_paid": paid_requests,
        "custom_requests_open": custom_count - paid_requests,
        "print_jobs_queued": print_jobs_queued,
        "low_inventory_count": low_inv,
        "low_filament_count": low_filament,
        "upcoming_markets": upcoming_markets,
    }


def product_analytics(limit: int = 20) -> list[dict]:
    from app.services.cost_engine import calculate_product_cost

    results = (
        db.session.query(
            Product.id,
            Product.name,
            Product.sku_base,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
            func.coalesce(func.sum(OrderItem.line_total), 0).label("revenue"),
            func.coalesce(func.avg(OrderItem.unit_price), 0).label("avg_price"),
        )
        .outerjoin(OrderItem, OrderItem.product_id == Product.id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.deleted_at.is_(None),
            Order.status == OrderStatus.COMPLETED,
        )
        .group_by(Product.id)
        .order_by(func.sum(OrderItem.line_total).desc())
        .limit(limit)
        .all()
    )

    products = []
    for r in results:
        product = db.session.get(Product, r[0])
        inv_count = 0
        if product:
            from app.models import InventoryRecord
            inv = (
                db.session.query(func.sum(InventoryRecord.quantity_on_hand))
                .filter(InventoryRecord.product_id == product.id)
                .scalar()
            )
            inv_count = int(inv or 0)

        failure_count = 0
        if product:
            failure_count = PrintJob.query.filter(
                PrintJob.product_id == product.id,
                PrintJob.status == PrintJobStatus.FAILED,
            ).count()

        breakdown = calculate_product_cost(product=product) if product is not None else None

        products.append({
            "id": r[0],
            "name": r[1],
            "sku": r[2],
            "units_sold": int(r[3]),
            "revenue": Decimal(str(r[4])),
            "avg_price": Decimal(str(r[5])) if r[5] else Decimal(0),
            "inventory_on_hand": inv_count,
            "failure_count": failure_count,
            "profit_per_unit": breakdown.profit_per_unit if breakdown is not None else Decimal("0.00"),
            "profit_per_print_hour": breakdown.profit_per_print_hour if breakdown is not None else Decimal("0.00"),
            "profit_per_market_bin_cm3": (
                breakdown.profit_per_market_bin_cm3 if breakdown is not None else Decimal("0.00")
            ),
            "cost_confidence": breakdown.confidence if breakdown is not None else "none",
        })

    return products


def market_analytics() -> list[dict]:
    markets = Market.query.filter(
        Market.status.in_([MarketStatus.COMPLETED, MarketStatus.REPEAT])
    ).order_by(Market.event_date.desc()).all()

    results = []
    for m in markets:
        total_sales = (
            db.session.query(func.sum(Order.total))
            .filter(Order.market_id == m.id, Order.deleted_at.is_(None))
            .scalar() or Decimal(0)
        )
        expenses = (
            db.session.query(func.sum(Expense.amount))
            .filter(Expense.related_market_id == m.id)
            .scalar() or Decimal(0)
        )
        booth_cost = (m.booth_fee or Decimal(0)) + (m.application_fee or Decimal(0))
        profit = total_sales - expenses - booth_cost

        units = (
            db.session.query(func.sum(OrderItem.quantity))
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.market_id == m.id, Order.deleted_at.is_(None))
            .scalar() or 0
        )

        results.append({
            "id": m.id,
            "name": m.name,
            "date": m.event_date,
            "total_sales": total_sales,
            "total_expenses": expenses,
            "booth_cost": booth_cost,
            "profit": profit,
            "units_sold": int(units),
            "status": m.status.value,
        })

    return results


def pos_analytics(days: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc).date()
    from datetime import timedelta
    start = cutoff - timedelta(days=days)

    sales = PosSale.query.filter(
        func.date(PosSale.created_at) >= start,
        PosSale.status == PosSaleStatus.COMPLETED,
    ).order_by(PosSale.created_at.desc()).all()

    total_revenue = sum(s.total for s in sales) if sales else Decimal(0)
    total_count = len(sales)
    avg_ticket = (total_revenue / Decimal(str(total_count))) if total_count > 0 else Decimal(0)

    payment_totals: dict[str, Decimal] = {}
    for s in sales:
        pm = str(s.payment_method)
        payment_totals[pm] = payment_totals.get(pm, Decimal(0)) + s.total

    sales_by_day: dict[str, Decimal] = {}
    for s in sales:
        day = s.created_at.strftime("%Y-%m-%d")
        sales_by_day[day] = sales_by_day.get(day, Decimal(0)) + s.total

    open_sessions = PosSession.query.filter(
        PosSession.status == PosSessionStatus.OPEN,
    ).count()

    return {
        "total_revenue": total_revenue,
        "total_sales": total_count,
        "avg_ticket": avg_ticket,
        "payment_totals": payment_totals,
        "sales_by_day": sales_by_day,
        "open_sessions": open_sessions,
        "days": days,
    }


def printing_analytics() -> dict:
    printers = Printer.query.order_by(Printer.name).all()

    printer_stats = []
    total_failures = 0
    total_completed = 0
    for p in printers:
        completed = PrintJob.query.filter(
            PrintJob.printer_id == p.id,
            PrintJob.status == PrintJobStatus.COMPLETED,
        ).count()
        failed = PrintJob.query.filter(
            PrintJob.printer_id == p.id,
            PrintJob.status == PrintJobStatus.FAILED,
        ).count()
        queued = PrintJob.query.filter(
            PrintJob.printer_id == p.id,
            PrintJob.status.in_([PrintJobStatus.QUEUED]),
        ).count()

        total_hours = (
            db.session.query(func.sum(PrintJob.actual_minutes))
            .filter(PrintJob.printer_id == p.id)
            .scalar() or 0
        )

        total_failures += failed
        total_completed += completed

        fail_rate = (failed / (completed + failed) * 100) if (completed + failed) > 0 else 0

        printer_stats.append({
            "id": p.id,
            "name": p.name,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "completed": completed,
            "failed": failed,
            "queued": queued,
            "total_hours": float(total_hours) / 60,
            "failure_rate": round(fail_rate, 1),
        })

    total_queued = PrintJob.query.filter(
        PrintJob.status.in_([PrintJobStatus.QUEUED])
    ).count()

    return {
        "printers": printer_stats,
        "total_completed": total_completed,
        "total_failures": total_failures,
        "total_queued": total_queued,
        "overall_failure_rate": round(
            (total_failures / (total_completed + total_failures) * 100)
            if (total_completed + total_failures) > 0 else 0, 1
        ),
    }


def inventory_analytics() -> dict:
    from app.models import FilamentSpool, FilamentStatus, InventoryRecord, InventoryLocation

    low_stock = (
        db.session.query(
            InventoryRecord.product_id,
            func.sum(InventoryRecord.quantity_on_hand).label("total_qty"),
        )
        .group_by(InventoryRecord.product_id)
        .having(func.sum(InventoryRecord.quantity_on_hand) <= 5)
        .all()
    )

    low_stock_count = len(low_stock)

    locations = InventoryLocation.query.filter_by(active=True).order_by(InventoryLocation.name).all()
    location_counts = []
    for loc in locations:
        qty = (
            db.session.query(func.coalesce(func.sum(InventoryRecord.quantity_on_hand), 0))
            .filter(InventoryRecord.location_id == loc.id)
            .scalar() or 0
        )
        location_counts.append({"name": loc.name, "quantity": int(qty)})

    total_inventory_value = (
        db.session.query(
            func.sum(InventoryRecord.quantity_on_hand * ProductVariant.price)
        )
        .join(ProductVariant, InventoryRecord.variant_id == ProductVariant.id)
        .scalar() or Decimal(0)
    )

    filament_low = FilamentSpool.query.filter(
        FilamentSpool.status == FilamentStatus.LOW
    ).count()
    filament_empty = FilamentSpool.query.filter(
        FilamentSpool.status == FilamentStatus.EMPTY
    ).count()

    return {
        "low_stock_count": low_stock_count,
        "location_counts": location_counts,
        "total_inventory_value": total_inventory_value,
        "filament_low": filament_low,
        "filament_empty": filament_empty,
    }


def expense_analytics(months: int = 6) -> dict:
    from datetime import timedelta
    start = (datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=180)).replace(day=1)

    by_category = (
        db.session.query(
            Expense.category,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(Expense.date >= start)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    category_data = [
        {
            "category": str(r[0].value) if hasattr(r[0], "value") else str(r[0]),
            "total": Decimal(str(r[1])),
            "count": int(r[2]),
        }
        for r in by_category
    ]

    all_expenses = Expense.query.filter(Expense.date >= start).order_by(Expense.date).all()
    monthly_totals: dict[str, Decimal] = {}
    for e in all_expenses:
        key = f"{e.date.year}-{e.date.month:02d}"
        monthly_totals[key] = monthly_totals.get(key, Decimal("0")) + e.amount

    monthly_data = [
        {"month": k, "total": v}
        for k, v in sorted(monthly_totals.items())
    ]

    total_all = sum(d["total"] for d in category_data)

    return {
        "by_category": category_data,
        "monthly_trend": monthly_data,
        "total_expenses": total_all,
        "months": months,
    }


def analytics_numbers_snapshot() -> dict:
    summary = executive_summary()
    pos = pos_analytics()
    inventory = inventory_analytics()
    expenses = expense_analytics()
    markets = market_analytics()[:5]
    products = product_analytics(limit=10)
    return {
        "summary": {
            "today_revenue": str(summary["today_revenue"]),
            "month_revenue": str(summary["month_revenue"]),
            "month_expenses": str(summary["month_expenses"]),
            "estimated_month_profit": str(summary["estimated_month_profit"]),
            "open_orders_count": summary["open_orders_count"],
            "low_inventory_count": summary["low_inventory_count"],
            "low_filament_count": summary["low_filament_count"],
        },
        "pos": {
            "total_revenue": str(pos["total_revenue"]),
            "total_sales": pos["total_sales"],
            "payment_totals": {k: str(v) for k, v in pos["payment_totals"].items()},
        },
        "inventory": {
            "low_stock_count": inventory["low_stock_count"],
            "total_inventory_value": str(inventory["total_inventory_value"]),
            "filament_low": inventory["filament_low"],
        },
        "expenses": {
            "total_expenses": str(expenses["total_expenses"]),
            "by_category": [
                {"category": row["category"], "total": str(row["total"])}
                for row in expenses["by_category"][:8]
            ],
        },
        "markets": [
            {"name": row["name"], "profit": str(row["profit"]), "total_sales": str(row["total_sales"])}
            for row in markets
        ],
        "products": [
            {"name": row["name"], "units_sold": row["units_sold"], "revenue": str(row["revenue"])}
            for row in products
        ],
    }


def analytics_insights() -> dict:
    from flask import current_app
    from app.services.audit import record_audit_event

    snapshot = analytics_numbers_snapshot()
    fallback = {
        "enabled": False,
        "insight": (
            "AI analytics insights are disabled. Review the numeric dashboard: prioritize low inventory, "
            "top-selling products, high-expense categories, and markets with positive profit."
        ),
        "numbers": snapshot,
    }
    if not current_app.config.get("AI_ANALYTICS_INSIGHTS_ENABLED", False):
        return fallback

    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        return fallback

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=current_app.config.get("OPENAI_MODEL_ANALYTICS", "gpt-4o-mini"),
            input=(
                "Explain these small-business 3D printing analytics. Keep the answer practical. "
                "Mention what changed, what to print next, which markets look repeatable, expenses "
                "hurting margin, and what needs attention. Always ground claims in the numbers.\n\n"
                + json.dumps(snapshot)
            ),
        )
        text = getattr(response, "output_text", None) or ""
        record_audit_event(
            action="analytics.ai_insight_generated",
            entity_type="analytics",
            entity_id="summary",
            after_state={"model": current_app.config.get("OPENAI_MODEL_ANALYTICS")},
            source_module=__name__,
        )
        return {"enabled": True, "insight": text, "numbers": snapshot}
    except Exception as exc:
        current_app.logger.warning("AI analytics insight generation failed: %s", exc)
        return fallback
