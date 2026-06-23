from __future__ import annotations

from app.extensions import db
from app.models import Order, OrderItem, Payment
from app.services.audit import record_audit_event
from app.services.crud import archive_instance


def _snapshot(instance) -> dict:
    data = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        data[column.name] = value
    return data


def create_order_resource(instance, *, actor_id: int | None = None):
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=f"{_entity_name(instance)}.created",
        entity_type=_entity_name(instance),
        entity_id=instance.id,
        after_state=_snapshot(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def update_order_resource(instance, *, before_state: dict, actor_id: int | None = None):
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=f"{_entity_name(instance)}.updated",
        entity_type=_entity_name(instance),
        entity_id=instance.id,
        before_state=before_state,
        after_state=_snapshot(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def archive_order_resource(instance, *, actor_id: int | None = None):
    before_state = _snapshot(instance)
    if isinstance(instance, OrderItem):
        db.session.delete(instance)
        db.session.commit()
        after_state = {"deleted": True}
        action = "order_item.deleted"
        entity_type = "order_item"
    else:
        archive_instance(instance)
        after_state = _snapshot(instance)
        action = f"{_entity_name(instance)}.archived"
        entity_type = _entity_name(instance)
    record_audit_event(
        action=action,
        entity_type=entity_type,
        entity_id=getattr(instance, "id", None),
        before_state=before_state,
        after_state=after_state,
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def snapshot_order_resource(instance) -> dict:
    return _snapshot(instance)


def _entity_name(instance) -> str:
    if isinstance(instance, Order):
        return "order"
    if isinstance(instance, Payment):
        return "payment"
    if isinstance(instance, OrderItem):
        return "order_item"
    return instance.__class__.__name__.lower()
