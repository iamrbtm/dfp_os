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
    actor_id: int | None = None,
) -> PrintJob:
    job = PrintJob(
        order_item=order_item,
        product_id=order_item.product_id,
        status=PrintJobStatus.QUEUED,
        priority=priority,
        estimated_minutes=estimated_minutes,
        label=label or f"Print for order item #{order_item.id}",
    )
    db.session.add(job)
    db.session.commit()
    record_audit_event(
        action="print_job.created",
        entity_type="print_job",
        entity_id=job.id,
        after_state={
            "status": job.status.value,
            "product_id": job.product_id,
            "order_item_id": job.order_item_id,
            "label": job.label,
        },
        source_module=__name__,
        actor_id=actor_id,
    )
    return job


def update_print_job_status(
    instance: PrintJob,
    new_status: PrintJobStatus,
    *,
    actor_id: int | None = None,
    failure_reason: str | None = None,
    filament_used_grams: int | None = None,
    actual_minutes: int | None = None,
) -> PrintJob:
    before_state = snapshot_instance(instance)
    instance.status = new_status
    if failure_reason:
        instance.failure_reason = failure_reason
    if filament_used_grams is not None:
        instance.filament_used_grams = filament_used_grams
    if actual_minutes is not None:
        instance.actual_minutes = actual_minutes
    db.session.add(instance)
    db.session.commit()

    action_map = {
        PrintJobStatus.COMPLETED: "print_job.completed",
        PrintJobStatus.FAILED: "print_job.failed",
        PrintJobStatus.PRINTING: "print_job.status_changed",
        PrintJobStatus.PAUSED: "print_job.status_changed",
        PrintJobStatus.CANCELLED: "print_job.status_changed",
        PrintJobStatus.QUEUED: "print_job.status_changed",
    }
    action = action_map.get(new_status, "print_job.status_changed")
    record_audit_event(
        action=action,
        entity_type="print_job",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_instance(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


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
