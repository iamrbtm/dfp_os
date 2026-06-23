from __future__ import annotations

from app.extensions import db
from app.models import Expense
from app.services.audit import record_audit_event
from app.services.crud import archive_instance


def snapshot_expense(expense: Expense) -> dict:
    data = {}
    for column in expense.__table__.columns:
        value = getattr(expense, column.name)
        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        elif value is not None:
            value = str(value)
        data[column.name] = value
    return data


def create_expense(expense: Expense, *, actor_id: int | None = None) -> Expense:
    db.session.add(expense)
    db.session.commit()
    record_audit_event(
        action="expense.created",
        entity_type="expense",
        entity_id=expense.id,
        after_state=snapshot_expense(expense),
        source_module=__name__,
        actor_id=actor_id,
    )
    return expense


def update_expense(expense: Expense, *, before_state: dict, actor_id: int | None = None) -> Expense:
    db.session.add(expense)
    db.session.commit()
    record_audit_event(
        action="expense.updated",
        entity_type="expense",
        entity_id=expense.id,
        before_state=before_state,
        after_state=snapshot_expense(expense),
        source_module=__name__,
        actor_id=actor_id,
    )
    return expense


def archive_expense(expense: Expense, *, actor_id: int | None = None) -> Expense:
    before_state = snapshot_expense(expense)
    archive_instance(expense)
    record_audit_event(
        action="expense.archived",
        entity_type="expense",
        entity_id=expense.id,
        before_state=before_state,
        after_state=snapshot_expense(expense),
        source_module=__name__,
        actor_id=actor_id,
    )
    return expense
