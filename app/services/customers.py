from __future__ import annotations

from app.extensions import db
from app.models import Customer
from app.services.audit import record_audit_event
from app.services.crud import archive_instance


def snapshot_customer(instance: Customer) -> dict:
    data = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        data[column.name] = value
    return data


def create_customer(instance: Customer, *, actor_id: int | None = None) -> Customer:
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action="customer.created",
        entity_type="customer",
        entity_id=instance.id,
        after_state=snapshot_customer(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def update_customer(instance: Customer, *, before_state: dict, actor_id: int | None = None) -> Customer:
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action="customer.updated",
        entity_type="customer",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_customer(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def archive_customer(instance: Customer, *, actor_id: int | None = None) -> Customer:
    before_state = snapshot_customer(instance)
    archive_instance(instance)
    record_audit_event(
        action="customer.archived",
        entity_type="customer",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_customer(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance
