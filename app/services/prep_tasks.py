from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    InventoryRecord,
    Market,
    Order,
    OrderItem,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    PrepTaskTemplate,
    Product,
)
from app.services.audit import record_audit_event


DEFAULT_TEMPLATES: tuple[tuple[str, PrepTaskCategory, int], ...] = (
    ("Count market-bin inventory", PrepTaskCategory.INVENTORY, 7),
    ("Print suggested restocks", PrepTaskCategory.REPRINT, 6),
    ("Pack bags, labels, tape, and repair kit", PrepTaskCategory.SUPPLY, 3),
    ("Prepare cash box and change", PrepTaskCategory.CASH_BOX, 2),
    ("Charge Square/card reader and payment devices", PrepTaskCategory.PAYMENT_DEVICE, 1),
    ("Pack signs, price tags, and QR code displays", PrepTaskCategory.SIGNAGE, 1),
)


def seed_default_prep_templates() -> int:
    created = 0
    for title, category, due_days in DEFAULT_TEMPLATES:
        existing = PrepTaskTemplate.query.filter_by(title=title).first()
        if existing is None:
            db.session.add(
                PrepTaskTemplate(
                    title=title,
                    category=category,
                    default_due_days_before=due_days,
                    default_enabled=True,
                )
            )
            created += 1
    if created:
        db.session.commit()
    return created


def suggested_quantities_for_market(market_id: int) -> list[dict[str, object]]:
    market = db.session.get(Market, market_id)
    if market is None:
        raise ValueError("Market not found")

    sold = (
        db.session.query(
            OrderItem.product_id,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.market_id == market_id, Order.deleted_at.is_(None))
        .group_by(OrderItem.product_id)
        .all()
    )
    historic = {row.product_id: int(row.units or 0) for row in sold if row.product_id}
    products = Product.query.filter(Product.deleted_at.is_(None), Product.is_pos_visible.is_(True)).all()

    suggestions = []
    for product in products:
        on_hand = (
            db.session.query(func.coalesce(func.sum(InventoryRecord.quantity_on_hand), 0))
            .filter(InventoryRecord.product_id == product.id)
            .scalar()
            or 0
        )
        recent_units = historic.get(product.id, 0)
        target = max(3, recent_units * 2 if recent_units else 5)
        gap = max(0, target - int(on_hand))
        suggestions.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "on_hand": int(on_hand),
                "suggested_quantity": target,
                "gap": gap,
            }
        )
    return sorted(suggestions, key=lambda row: (row["gap"], row["suggested_quantity"]), reverse=True)


def generate_market_prep_tasks(market_id: int, actor_id: int | None = None) -> list[PrepTask]:
    market = db.session.get(Market, market_id)
    if market is None:
        raise ValueError("Market not found")

    seed_default_prep_templates()
    templates = PrepTaskTemplate.query.filter_by(default_enabled=True).all()
    generated: list[PrepTask] = []
    event_date = market.event_date
    event_start = (
        datetime.combine(event_date, time(hour=9), tzinfo=timezone.utc)
        if event_date is not None
        else None
    )
    for template in templates:
        existing = PrepTask.query.filter_by(market_id=market_id, template_id=template.id).first()
        if existing:
            continue
        due_at = None
        if event_start is not None:
            from datetime import timedelta

            due_at = event_start - timedelta(days=template.default_due_days_before)
        task = PrepTask(
            market_id=market_id,
            template_id=template.id,
            title=template.title,
            category=template.category,
            due_at=due_at,
            source="template",
        )
        db.session.add(task)
        generated.append(task)

    for suggestion in suggested_quantities_for_market(market_id)[:10]:
        if suggestion["gap"] <= 0:
            continue
        title = f"Reprint {suggestion['gap']} x {suggestion['product_name']}"
        existing = PrepTask.query.filter_by(market_id=market_id, title=title).first()
        if existing is None:
            task = PrepTask(
                market_id=market_id,
                title=title,
                category=PrepTaskCategory.REPRINT,
                source="inventory_gap",
                notes=f"Target {suggestion['suggested_quantity']}; on hand {suggestion['on_hand']}.",
            )
            db.session.add(task)
            generated.append(task)

    db.session.commit()
    for task in generated:
        record_audit_event(
            action="prep_task.generated",
            entity_type="prep_task",
            entity_id=task.id,
            after_state={"title": task.title, "market_id": task.market_id, "source": task.source},
            source_module=__name__,
            actor_id=actor_id,
        )
    return generated


def market_readiness_score(market_id: int) -> dict[str, object]:
    tasks = PrepTask.query.filter_by(market_id=market_id).all()
    if not tasks:
        return {"score": Decimal("0.00"), "completed": 0, "total": 0, "summary": "No prep tasks generated."}
    completed = sum(1 for task in tasks if task.status == PrepTaskStatus.COMPLETED)
    score = (Decimal(completed) / Decimal(len(tasks)) * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "score": score,
        "completed": completed,
        "total": len(tasks),
        "summary": f"{completed} of {len(tasks)} prep tasks complete.",
    }
