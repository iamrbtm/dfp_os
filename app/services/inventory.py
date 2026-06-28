from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from app.extensions import db
from app.models import InventoryMovement, InventoryMovementType, InventoryRecord
from app.services.audit import record_audit_event


@dataclass(frozen=True)
class DeductionResult:
    requested: int
    deducted: int
    remaining_short: int


def allow_negative_inventory() -> bool:
    return bool(current_app.config.get("ALLOW_NEGATIVE_INVENTORY", False))


def record_movement(
    *,
    movement_type: InventoryMovementType,
    quantity: int,
    inventory_record: InventoryRecord | None = None,
    product_id: int | None = None,
    from_location_id: int | None = None,
    to_location_id: int | None = None,
    reference_type: str | None = None,
    reference_id: str | int | None = None,
    actor_id: int | None = None,
    notes: str | None = None,
) -> InventoryMovement:
    movement = InventoryMovement(
        inventory_record_id=inventory_record.id if inventory_record else None,
        product_id=product_id if product_id is not None else getattr(inventory_record, "product_id", None),
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        quantity=quantity,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id is not None else None,
        actor_id=actor_id,
        notes=notes,
    )
    db.session.add(movement)
    return movement


def get_or_create_inventory_record(
    *,
    product_id: int,
    location_id: int,
) -> InventoryRecord:
    record = InventoryRecord.query.filter_by(
        product_id=product_id,
        location_id=location_id,
    ).with_for_update().first()
    if record is None:
        record = InventoryRecord(
            product_id=product_id,
            location_id=location_id,
            quantity_on_hand=0,
            quantity_reserved=0,
        )
        db.session.add(record)
        db.session.flush()
    return record


def deduct_finished_goods(
    *,
    product_id: int,
    quantity: int,
    location_id: int | None,
    reference_type: str,
    reference_id: str | int,
    actor_id: int | None = None,
) -> DeductionResult:
    if quantity <= 0:
        return DeductionResult(requested=quantity, deducted=0, remaining_short=0)

    query = InventoryRecord.query.filter(
        InventoryRecord.product_id == product_id,
        InventoryRecord.quantity_on_hand > 0,
    )
    if location_id is not None:
        query = query.filter(InventoryRecord.location_id == location_id)

    records = query.order_by(InventoryRecord.id).with_for_update().all()
    available = sum(record.quantity_on_hand for record in records)
    if available < quantity and not allow_negative_inventory():
        raise ValueError(
            f"Insufficient inventory for product {product_id}: requested {quantity}, available {available}."
        )

    remaining = quantity
    deducted = 0
    for record in records:
        if remaining <= 0:
            break
        amount = min(remaining, record.quantity_on_hand)
        before = {
            "quantity_on_hand": record.quantity_on_hand,
            "quantity_reserved": record.quantity_reserved,
        }
        record.quantity_on_hand -= amount
        remaining -= amount
        deducted += amount
        record_movement(
            movement_type=InventoryMovementType.DEDUCTION,
            quantity=amount,
            inventory_record=record,
            from_location_id=record.location_id,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
        )
        record_audit_event(
            action="inventory.deducted",
            entity_type="inventory_record",
            entity_id=record.id,
            before_state=before,
            after_state={
                "quantity_on_hand": record.quantity_on_hand,
                "quantity_reserved": record.quantity_reserved,
            },
            metadata={"reference_type": reference_type, "reference_id": str(reference_id)},
            source_module=__name__,
        )

    if remaining > 0 and allow_negative_inventory():
        record = records[0] if records else None
        if record is None:
            record = InventoryRecord(
                product_id=product_id,
                location_id=location_id,
                quantity_on_hand=0,
                quantity_reserved=0,
            )
            db.session.add(record)
            db.session.flush()
        record.quantity_on_hand -= remaining
        deducted += remaining
        record_movement(
            movement_type=InventoryMovementType.DEDUCTION,
            quantity=remaining,
            inventory_record=record,
            from_location_id=record.location_id,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
            notes="Negative inventory allowed by configuration.",
        )
        remaining = 0

    return DeductionResult(requested=quantity, deducted=deducted, remaining_short=remaining)


def adjust_inventory(
    *,
    record_id: int,
    quantity_delta: int,
    actor_id: int | None = None,
    notes: str | None = None,
) -> InventoryRecord:
    record = db.session.get(InventoryRecord, record_id)
    if record is None:
        raise ValueError("Inventory record not found")
    before = {
        "quantity_on_hand": record.quantity_on_hand,
        "quantity_reserved": record.quantity_reserved,
    }
    new_quantity = record.quantity_on_hand + quantity_delta
    if new_quantity < 0 and not allow_negative_inventory():
        raise ValueError("Inventory adjustment would make quantity negative")
    record.quantity_on_hand = new_quantity
    record_movement(
        movement_type=InventoryMovementType.ADJUSTMENT,
        quantity=quantity_delta,
        inventory_record=record,
        to_location_id=record.location_id if quantity_delta > 0 else None,
        from_location_id=record.location_id if quantity_delta < 0 else None,
        actor_id=actor_id,
        notes=notes,
    )
    record_audit_event(
        action="inventory.adjusted",
        entity_type="inventory_record",
        entity_id=record.id,
        before_state=before,
        after_state={
            "quantity_on_hand": record.quantity_on_hand,
            "quantity_reserved": record.quantity_reserved,
        },
        metadata={"quantity_delta": quantity_delta, "notes": notes},
        source_module=__name__,
    )
    return record


def transfer_inventory(
    *,
    record_id: int,
    to_location_id: int,
    quantity: int,
    actor_id: int | None = None,
    notes: str | None = None,
) -> tuple[InventoryRecord, InventoryRecord]:
    if quantity <= 0:
        raise ValueError("Transfer quantity must be greater than zero")

    source = db.session.get(InventoryRecord, record_id)
    if source is None:
        raise ValueError("Inventory record not found")
    if source.location_id == to_location_id:
        raise ValueError("Choose a different destination location")
    if source.quantity_available < quantity and not allow_negative_inventory():
        raise ValueError("Transfer quantity exceeds available stock")

    source_before = {
        "quantity_on_hand": source.quantity_on_hand,
        "quantity_reserved": source.quantity_reserved,
        "location_id": source.location_id,
    }
    destination = get_or_create_inventory_record(
        product_id=source.product_id,
        location_id=to_location_id,
    )
    dest_before = {
        "quantity_on_hand": destination.quantity_on_hand,
        "quantity_reserved": destination.quantity_reserved,
        "location_id": destination.location_id,
    }

    source.quantity_on_hand -= quantity
    destination.quantity_on_hand += quantity

    record_movement(
        movement_type=InventoryMovementType.TRANSFER_OUT,
        quantity=quantity,
        inventory_record=source,
        from_location_id=source.location_id,
        to_location_id=to_location_id,
        actor_id=actor_id,
        notes=notes,
    )
    record_movement(
        movement_type=InventoryMovementType.TRANSFER_IN,
        quantity=quantity,
        inventory_record=destination,
        from_location_id=source.location_id,
        to_location_id=to_location_id,
        actor_id=actor_id,
        notes=notes,
    )
    record_audit_event(
        action="inventory.transferred",
        entity_type="inventory_record",
        entity_id=source.id,
        before_state=source_before,
        after_state={
            "quantity_on_hand": source.quantity_on_hand,
            "quantity_reserved": source.quantity_reserved,
            "location_id": source.location_id,
        },
        metadata={"to_location_id": to_location_id, "quantity": quantity, "notes": notes},
        source_module=__name__,
        actor_id=actor_id,
    )
    record_audit_event(
        action="inventory.transfer_received",
        entity_type="inventory_record",
        entity_id=destination.id,
        before_state=dest_before,
        after_state={
            "quantity_on_hand": destination.quantity_on_hand,
            "quantity_reserved": destination.quantity_reserved,
            "location_id": destination.location_id,
        },
        metadata={"from_record_id": source.id, "quantity": quantity, "notes": notes},
        source_module=__name__,
        actor_id=actor_id,
    )
    return source, destination


def reserve_inventory(
    *,
    record_id: int,
    quantity: int,
    actor_id: int | None = None,
    notes: str | None = None,
) -> InventoryRecord:
    if quantity <= 0:
        raise ValueError("Reservation quantity must be greater than zero")
    record = db.session.get(InventoryRecord, record_id)
    if record is None:
        raise ValueError("Inventory record not found")
    if record.quantity_available < quantity and not allow_negative_inventory():
        raise ValueError("Reservation quantity exceeds available stock")

    before = {
        "quantity_on_hand": record.quantity_on_hand,
        "quantity_reserved": record.quantity_reserved,
    }
    record.quantity_reserved += quantity
    record_movement(
        movement_type=InventoryMovementType.RESERVATION,
        quantity=quantity,
        inventory_record=record,
        to_location_id=record.location_id,
        actor_id=actor_id,
        notes=notes,
    )
    record_audit_event(
        action="inventory.reserved",
        entity_type="inventory_record",
        entity_id=record.id,
        before_state=before,
        after_state={
            "quantity_on_hand": record.quantity_on_hand,
            "quantity_reserved": record.quantity_reserved,
        },
        metadata={"quantity": quantity, "notes": notes},
        source_module=__name__,
        actor_id=actor_id,
    )
    return record


def release_inventory(
    *,
    record_id: int,
    quantity: int,
    actor_id: int | None = None,
    notes: str | None = None,
) -> InventoryRecord:
    if quantity <= 0:
        raise ValueError("Release quantity must be greater than zero")
    record = db.session.get(InventoryRecord, record_id)
    if record is None:
        raise ValueError("Inventory record not found")
    if record.quantity_reserved < quantity:
        raise ValueError("Release quantity exceeds reserved stock")

    before = {
        "quantity_on_hand": record.quantity_on_hand,
        "quantity_reserved": record.quantity_reserved,
    }
    record.quantity_reserved -= quantity
    record_movement(
        movement_type=InventoryMovementType.RELEASE,
        quantity=quantity,
        inventory_record=record,
        from_location_id=record.location_id,
        actor_id=actor_id,
        notes=notes,
    )
    record_audit_event(
        action="inventory.released",
        entity_type="inventory_record",
        entity_id=record.id,
        before_state=before,
        after_state={
            "quantity_on_hand": record.quantity_on_hand,
            "quantity_reserved": record.quantity_reserved,
        },
        metadata={"quantity": quantity, "notes": notes},
        source_module=__name__,
        actor_id=actor_id,
    )
    return record


def return_inventory(
    *,
    product_id: int,
    quantity: int,
    location_id: int | None,
    reference_type: str,
    reference_id: str | int,
    actor_id: int | None = None,
    notes: str | None = None,
) -> InventoryRecord:
    if quantity <= 0:
        raise ValueError("Return quantity must be greater than zero")
    if location_id is None:
        raise ValueError("A destination location is required to return inventory")

    record = get_or_create_inventory_record(
        product_id=product_id,
        location_id=location_id,
    )
    before = {
        "quantity_on_hand": record.quantity_on_hand,
        "quantity_reserved": record.quantity_reserved,
    }
    record.quantity_on_hand += quantity
    record_movement(
        movement_type=InventoryMovementType.RETURN,
        quantity=quantity,
        inventory_record=record,
        to_location_id=location_id,
        reference_type=reference_type,
        reference_id=reference_id,
        actor_id=actor_id,
        notes=notes,
    )
    record_audit_event(
        action="inventory.returned",
        entity_type="inventory_record",
        entity_id=record.id,
        before_state=before,
        after_state={
            "quantity_on_hand": record.quantity_on_hand,
            "quantity_reserved": record.quantity_reserved,
        },
        metadata={"reference_type": reference_type, "reference_id": str(reference_id), "quantity": quantity, "notes": notes},
        source_module=__name__,
        actor_id=actor_id,
    )
    return record
