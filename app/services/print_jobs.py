from __future__ import annotations

from app.extensions import db
from app.models import OrderItem, PrintJob, PrintJobStatus
from app.services.admin_mutations import create_resource, snapshot_instance, update_resource
from app.services.audit import record_audit_event


def create_print_job(instance: PrintJob, *, actor_id: int | None = None) -> PrintJob:
    return create_resource(instance, actor_id=actor_id, entity_type="print_job")


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


def update_print_job(instance: PrintJob, *, before_state: dict, actor_id: int | None = None) -> PrintJob:
    return update_resource(instance, before_state=before_state, actor_id=actor_id, entity_type="print_job")


def archive_print_job(instance: PrintJob, *, actor_id: int | None = None) -> PrintJob:
    before_state = snapshot_instance(instance)
    instance.status = PrintJobStatus.CANCELLED
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action="print_job.archived",
        entity_type="print_job",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_instance(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance
