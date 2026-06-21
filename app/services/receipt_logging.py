"""Receipt logging — sends structured audit events to the audit-log microservice.

This replaces the old stdout logging with proper audit-log microservice calls.
All log functions delegate to receipt_audit which uses AuditClient.
Kept as a thin facade so importers don't need refactoring.
"""

from __future__ import annotations

from typing import Any

from app.services.receipt_audit import (
    log_processing_result,
    log_upload,
    record_audit,
)


def log_event(
    event: str,
    receipt_id: int | None = None,
    level: str = "info",
    details: dict[str, Any] | None = None,
    exception: BaseException | None = None,
):
    if receipt_id is not None:
        record_audit(
            receipt_id=receipt_id,
            action=event,
            details=str(details or {}),
        )
    if exception:
        import logging
        logging.getLogger("dfp_os.receipts").error(
            "event=%s receipt_id=%s error=%s",
            event, receipt_id, exception,
            exc_info=exception,
        )


def log_upload_event(
    receipt_id: int,
    filename: str,
    file_size: int,
    user_id: int,
):
    log_upload(receipt_id, filename, file_size, user_id)


def log_processing_start(receipt_id: int, step: str):
    log_processing_result(receipt_id, step, True, {"status": "started"})


def log_processing_complete(receipt_id: int, step: str, success: bool, diagnostics: dict[str, Any] | None = None):
    log_processing_result(receipt_id, step, success, diagnostics)


def log_error(receipt_id: int | None, message: str, exception: BaseException | None = None):
    if receipt_id is not None:
        record_audit(
            receipt_id=receipt_id,
            action="receipt.error",
            details=message,
        )
    if exception:
        import logging
        logging.getLogger("dfp_os.receipts").error(
            "receipt_id=%s message=%s error=%s",
            receipt_id, message, exception,
            exc_info=exception,
        )
