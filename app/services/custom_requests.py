from __future__ import annotations

from app.extensions import db
from app.models import CustomRequest, CustomRequestStatus
from app.services.audit import record_audit_event
from app.utils.audit_events import AuditAction


def snapshot_custom_request(instance: CustomRequest) -> dict:
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


def create_custom_request(
    instance: CustomRequest, *, actor_id: int | None = None, actor_type: str | None = None
) -> CustomRequest:
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=AuditAction.CUSTOM_REQUEST_CREATED.value,
        entity_type="custom_request",
        entity_id=instance.id,
        after_state=snapshot_custom_request(instance),
        source_module=__name__,
        actor_id=actor_id,
        actor_type=actor_type,
    )
    return instance


def update_custom_request(
    instance: CustomRequest,
    *,
    before_state: dict,
    actor_id: int | None = None,
    actor_type: str | None = None,
) -> CustomRequest:
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=AuditAction.CUSTOM_REQUEST_UPDATED.value,
        entity_type="custom_request",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_custom_request(instance),
        source_module=__name__,
        actor_id=actor_id,
        actor_type=actor_type,
    )
    return instance


def archive_custom_request(
    instance: CustomRequest,
    *,
    actor_id: int | None = None,
    actor_type: str | None = None,
) -> CustomRequest:
    before_state = snapshot_custom_request(instance)
    instance.status = CustomRequestStatus.ARCHIVED
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=AuditAction.CUSTOM_REQUEST_STATUS_CHANGED.value,
        entity_type="custom_request",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_custom_request(instance),
        source_module=__name__,
        actor_id=actor_id,
        actor_type=actor_type,
    )
    return instance


def convert_custom_request(
    instance: CustomRequest,
    *,
    actor_id: int | None = None,
    actor_type: str | None = None,
) -> CustomRequest:
    before_state = snapshot_custom_request(instance)
    instance.status = CustomRequestStatus.CONVERTED
    db.session.add(instance)
    db.session.commit()
    record_audit_event(
        action=AuditAction.CUSTOM_REQUEST_CONVERTED.value,
        entity_type="custom_request",
        entity_id=instance.id,
        before_state=before_state,
        after_state=snapshot_custom_request(instance),
        source_module=__name__,
        actor_id=actor_id,
        actor_type=actor_type,
    )
    return instance
