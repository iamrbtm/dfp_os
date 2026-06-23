from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.audit_client import get_audit_client


def record_audit(
    receipt_id: int,
    action: str,
    user_id: int | None = None,
    details: str | None = None,
    *,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
):
    client = get_audit_client()
    metadata = {}
    if details:
        try:
            import json
            metadata = json.loads(details) if isinstance(details, str) else {"details": details}
        except (ValueError, TypeError):
            metadata = {"details": str(details)}

    client.record(
        action=action,
        entity_type="receipt",
        entity_id=str(receipt_id),
        actor_id=str(user_id) if user_id else None,
        actor_type="user" if user_id else None,
        source_service="dfp-os",
        source_module="receipts",
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )


def snapshot_receipt(receipt) -> dict[str, Any]:
    fields = [
        "status",
        "merchant_name",
        "store_name",
        "store_number",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "phone",
        "receipt_number",
        "transaction_number",
        "payment_method",
        "currency",
        "subtotal",
        "tax_total",
        "fee_total",
        "discount_total",
        "tip_total",
        "deposit_total",
        "grand_total",
        "date_time",
        "notes",
    ]
    return {field: _serialize_value(getattr(receipt, field, None)) for field in fields}


def snapshot_line_item(item) -> dict[str, Any]:
    fields = [
        "description",
        "sku",
        "quantity",
        "unit_price",
        "line_total",
        "line_tax",
        "needs_review",
        "is_inventory_candidate",
        "is_personal_or_excluded",
    ]
    return {field: _serialize_value(getattr(item, field, None)) for field in fields}


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def log_upload(
    receipt_id: int,
    filename: str,
    file_size: int,
    user_id: int,
):
    client = get_audit_client()
    client.record(
        action="receipt.uploaded",
        entity_type="receipt",
        entity_id=str(receipt_id),
        actor_id=str(user_id),
        actor_type="user",
        source_service="dfp-os",
        source_module="receipts",
        metadata={
            "filename": filename,
            "file_size": file_size,
        },
    )


def log_processing_result(
    receipt_id: int,
    step: str,
    success: bool,
    diagnostics: dict[str, Any] | None = None,
):
    client = get_audit_client()
    client.record(
        action=f"receipt.processing.{step}.{'complete' if success else 'failed'}",
        entity_type="receipt",
        entity_id=str(receipt_id),
        source_service="dfp-os",
        source_module="receipts",
        metadata={"success": success, "diagnostics": diagnostics or {}},
    )


def log_ocr_result(
    receipt_id: int,
    provider: str,
    line_count: int,
    confidence: float | None,
):
    client = get_audit_client()
    client.record(
        action="receipt.ocr.complete",
        entity_type="receipt",
        entity_id=str(receipt_id),
        source_service="dfp-os",
        source_module="receipts",
        metadata={
            "provider": provider,
            "line_count": line_count,
            "confidence": confidence,
        },
    )


def log_ai_extraction(
    receipt_id: int,
    model: str,
    confidence: float | None,
    retry: bool = False,
):
    client = get_audit_client()
    client.record(
        action="receipt.ai.extraction",
        entity_type="receipt",
        entity_id=str(receipt_id),
        source_service="dfp-os",
        source_module="receipts",
        metadata={
            "model": model,
            "confidence": confidence,
            "retry": retry,
        },
    )


def log_approval(
    receipt_id: int,
    user_id: int,
    line_item_count: int,
):
    client = get_audit_client()
    client.record(
        action="receipt.approved",
        entity_type="receipt",
        entity_id=str(receipt_id),
        actor_id=str(user_id),
        actor_type="user",
        source_service="dfp-os",
        source_module="receipts",
        metadata={"line_items": line_item_count},
    )


def log_rejection(receipt_id: int, user_id: int):
    client = get_audit_client()
    client.record(
        action="receipt.rejected",
        entity_type="receipt",
        entity_id=str(receipt_id),
        actor_id=str(user_id),
        actor_type="user",
        source_service="dfp-os",
        source_module="receipts",
    )


def log_duplicate_check(
    receipt_id: int,
    score: int,
    is_duplicate: bool,
    match_count: int,
):
    client = get_audit_client()
    client.record(
        action="receipt.duplicate_check",
        entity_type="receipt",
        entity_id=str(receipt_id),
        source_service="dfp-os",
        source_module="receipts",
        metadata={
            "score": score,
            "is_duplicate": is_duplicate,
            "matches": match_count,
        },
    )


def log_allocation(
    receipt_id: int,
    line_item_count: int,
    allocation_type: str,
):
    client = get_audit_client()
    client.record(
        action="receipt.allocation",
        entity_type="receipt",
        entity_id=str(receipt_id),
        source_service="dfp-os",
        source_module="receipts",
        metadata={
            "line_items": line_item_count,
            "type": allocation_type,
        },
    )
