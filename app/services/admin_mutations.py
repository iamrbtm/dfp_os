from __future__ import annotations

import re

from app.extensions import db
from app.services.audit import record_audit_event
from app.services.crud import archive_instance


def snapshot_instance(instance) -> dict:
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


def create_resource(instance, *, actor_id: int | None = None, entity_type: str | None = None):
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=f"{_entity_name(instance, entity_type)}.created",
        entity_type=_entity_name(instance, entity_type),
        entity_id=instance.id,
        after_state=snapshot_instance(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def update_resource(instance, *, before_state: dict, actor_id: int | None = None, entity_type: str | None = None):
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=f"{_entity_name(instance, entity_type)}.updated",
        entity_type=_entity_name(instance, entity_type),
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_instance(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def archive_resource(instance, *, actor_id: int | None = None, entity_type: str | None = None):
    before_state = snapshot_instance(instance)
    archive_instance(instance)
    record_audit_event(
        action=f"{_entity_name(instance, entity_type)}.archived",
        entity_type=_entity_name(instance, entity_type),
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_instance(instance),
        source_module=__name__,
        actor_id=actor_id,
    )
    return instance


def _entity_name(instance, explicit: str | None) -> str:
    if explicit:
        return explicit
    name = instance.__class__.__name__
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()
