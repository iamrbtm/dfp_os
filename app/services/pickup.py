from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select

from app.extensions import db
from app.models import (
    CustomRequest,
    Order,
    PickupSlot,
    PickupSlotStatus,
    PickupStatus,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
)
from app.services.admin_mutations import snapshot_instance
from app.services.audit import record_audit_event


class PickupError(ValueError):
    pass


@dataclass(frozen=True)
class PickupBoardGroup:
    slot: PickupSlot
    orders: list[Order]
    custom_requests: list[CustomRequest]

    @property
    def total_items(self) -> int:
        return len(self.orders) + len(self.custom_requests)


def available_pickup_slots(now: datetime | None = None) -> list[PickupSlot]:
    now = now or datetime.now(timezone.utc)
    return list(
        db.session.scalars(
            select(PickupSlot)
            .where(
                PickupSlot.status == PickupSlotStatus.OPEN,
                PickupSlot.starts_at >= now,
            )
            .order_by(PickupSlot.starts_at.asc())
        )
    )


def validate_pickup_slot(slot: PickupSlot, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    starts_at = slot.starts_at
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    if slot.status != PickupSlotStatus.OPEN:
        raise PickupError("That pickup window is not available.")
    if starts_at < now:
        raise PickupError("That pickup window has already passed.")
    if slot.available_capacity <= 0:
        slot.status = PickupSlotStatus.FULL
        db.session.add(slot)
        db.session.flush()
        raise PickupError("That pickup window is full.")


def assign_order_pickup(order: Order, slot: PickupSlot | None, *, notes: str | None = None, actor_id: int | None = None) -> Order:
    before_state = snapshot_instance(order)
    if slot is None:
        order.pickup_slot_id = None
        order.pickup_status = None
        order.pickup_notes = notes
    else:
        validate_pickup_slot(slot)
        order.pickup_slot = slot
        order.pickup_status = PickupStatus.SCHEDULED.value
        order.pickup_notes = notes
    db.session.add(order)
    db.session.commit()
    _audit("order.pickup_scheduled", "order", order.id, before_state, snapshot_instance(order), actor_id)
    return order


def assign_custom_request_pickup(
    custom_request: CustomRequest,
    slot: PickupSlot | None,
    *,
    notes: str | None = None,
    actor_id: int | None = None,
) -> CustomRequest:
    before_state = snapshot_instance(custom_request)
    if slot is None:
        custom_request.pickup_slot_id = None
        custom_request.pickup_status = None
        custom_request.pickup_notes = notes
    else:
        validate_pickup_slot(slot)
        custom_request.pickup_slot = slot
        custom_request.pickup_status = PickupStatus.SCHEDULED.value
        custom_request.pickup_notes = notes
    db.session.add(custom_request)
    db.session.commit()
    _audit(
        "custom_request.pickup_scheduled",
        "custom_request",
        custom_request.id,
        before_state,
        snapshot_instance(custom_request),
        actor_id,
    )
    return custom_request


def transition_pickup(entity: Order | CustomRequest, status: PickupStatus, *, actor_id: int | None = None) -> Order | CustomRequest:
    before_state = snapshot_instance(entity)
    now = datetime.now(timezone.utc)
    entity.pickup_status = status.value
    if status == PickupStatus.READY:
        entity.pickup_ready_at = now
    elif status == PickupStatus.HANDED_OFF:
        entity.picked_up_at = now
    elif status == PickupStatus.NO_SHOW:
        entity.pickup_no_show_at = now
    db.session.add(entity)
    db.session.commit()
    entity_type = "order" if isinstance(entity, Order) else "custom_request"
    _audit(f"{entity_type}.pickup_{status.value}", entity_type, entity.id, before_state, snapshot_instance(entity), actor_id)
    return entity


def pickup_board_groups() -> list[PickupBoardGroup]:
    slots = list(
        db.session.scalars(
            select(PickupSlot)
            .where(PickupSlot.status.in_([PickupSlotStatus.OPEN, PickupSlotStatus.FULL, PickupSlotStatus.CLOSED]))
            .order_by(PickupSlot.starts_at.asc())
        )
    )
    return [
        PickupBoardGroup(
            slot=slot,
            orders=[order for order in slot.orders if order.pickup_status != PickupStatus.CANCELED.value],
            custom_requests=[
                request for request in slot.custom_requests if request.pickup_status != PickupStatus.CANCELED.value
            ],
        )
        for slot in slots
        if slot.orders or slot.custom_requests
    ]


def generate_pickup_batch_prep_tasks(groups: Iterable[PickupBoardGroup], *, actor_id: int | None = None) -> int:
    count = 0
    for group in groups:
        title = f"Prep pickup batch: {group.slot.public_label or group.slot.location.name}"
        existing = PrepTask.query.filter_by(
            title=title,
            source="pickup_scheduler",
            due_at=group.slot.starts_at,
        ).first()
        if existing:
            continue
        db.session.add(
            PrepTask(
                title=title,
                category=PrepTaskCategory.FOLLOW_UP,
                status=PrepTaskStatus.OPEN,
                due_at=group.slot.starts_at,
                source="pickup_scheduler",
                notes=f"{group.total_items} pickup item(s) scheduled for this window.",
                follow_up_type="pickup_reminder",
                market_id=group.slot.market_id,
            )
        )
        count += 1
    db.session.commit()
    if count:
        record_audit_event(
            action="pickup_batch.prep_tasks_generated",
            entity_type="pickup_batch",
            entity_id="batch",
            after_state={"task_count": count},
            source_module=__name__,
            actor_id=actor_id,
        )
    return count


def pickup_board_summary() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for order in Order.query.filter(Order.pickup_slot_id.is_not(None)).all():
        counts[order.pickup_status or "unscheduled"] += 1
    for custom_request in CustomRequest.query.filter(CustomRequest.pickup_slot_id.is_not(None)).all():
        counts[custom_request.pickup_status or "unscheduled"] += 1
    return dict(counts)


def _audit(action: str, entity_type: str, entity_id: int, before_state: dict | None, after_state: dict | None, actor_id: int | None) -> None:
    record_audit_event(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        source_module=__name__,
        actor_id=actor_id,
    )
