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
    variant_id: int | None = None,
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
        variant_id=variant_id if variant_id is not None else getattr(inventory_record, "variant_id", None),
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


def deduct_finished_goods(
    *,
    product_id: int,
    variant_id: int | None,
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
    if variant_id is not None:
        query = query.filter(InventoryRecord.variant_id == variant_id)
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
                variant_id=variant_id,
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
