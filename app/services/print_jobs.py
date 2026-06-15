from __future__ import annotations

from app.extensions import db
from app.models import OrderItem, PrintJob, PrintJobStatus


def create_print_job_from_order_item(
    order_item: OrderItem,
    label: str | None = None,
    priority: int = 0,
    estimated_minutes: int = 0,
) -> PrintJob:
    job = PrintJob(
        order_item=order_item,
        product_id=order_item.product_id,
        variant_id=order_item.variant_id,
        status=PrintJobStatus.QUEUED,
        priority=priority,
        estimated_minutes=estimated_minutes,
        label=label or f"Print for order item #{order_item.id}",
    )
    db.session.add(job)
    db.session.commit()
    return job
