"""Canonical audit action names.

Every audit event emitted by the app MUST use a value from this module.
Centralising the list keeps the audit viewer filterable, the production
readiness scorecard honest, and the coverage test enforceable.

Names are dotted past-tense verbs: ``<module>.<verb>``.
"""

from __future__ import annotations

from enum import Enum


class AuditAction(str, Enum):
    # ── Authentication / users ──────────────────────────────────────────
    USER_LOGIN_SUCCEEDED = "user.login_succeeded"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOGOUT = "user.logout"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    USER_ROLE_CHANGED = "user.role_changed"
    API_TOKEN_CREATED = "api_token.created"
    API_TOKEN_REVOKED = "api_token.revoked"

    # ── Settings / feature flags / modules ──────────────────────────────
    SETTING_CHANGED = "setting.changed"
    FEATURE_FLAG_CHANGED = "feature_flag.changed"
    MODULE_ENABLED = "module.enabled"
    MODULE_DISABLED = "module.disabled"
    MODULE_DISABLED_ACCESS_ATTEMPTED = "module.disabled_access_attempted"
    FAILED_AUTHORIZATION = "auth.failed_authorization"

    # ── Products / variants / models ────────────────────────────────────
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_ARCHIVED = "product.archived"
    PRODUCT_RESTORED = "product.restored"
    VARIANT_CREATED = "variant.created"
    VARIANT_UPDATED = "variant.updated"
    VARIANT_ARCHIVED = "variant.archived"
    VARIANT_RESTORED = "variant.restored"
    MODEL_ASSET_LICENSE_TRACKED = "model_asset.license_tracked"

    # ── Printers / AMS / filament ────────────────────────────────────────
    PRINTER_CREATED = "printer.created"
    PRINTER_UPDATED = "printer.updated"
    PRINTER_ARCHIVED = "printer.archived"
    AMS_UNIT_CREATED = "ams_unit.created"
    AMS_UNIT_UPDATED = "ams_unit.updated"
    AMS_UNIT_ARCHIVED = "ams_unit.archived"
    FILAMENT_SPOOL_CREATED = "filament_spool.created"
    FILAMENT_SPOOL_UPDATED = "filament_spool.updated"
    FILAMENT_SPOOL_ARCHIVED = "filament_spool.archived"

    # ── Inventory ───────────────────────────────────────────────────────
    INVENTORY_ADJUSTED = "inventory.adjusted"
    INVENTORY_TRANSFERRED = "inventory.transferred"
    INVENTORY_DEDUCTED = "inventory.deducted"
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_RELEASED = "inventory.released"

    # ── Print jobs ──────────────────────────────────────────────────────
    PRINT_JOB_CREATED = "print_job.created"
    PRINT_JOB_UPDATED = "print_job.updated"
    PRINT_JOB_STATUS_CHANGED = "print_job.status_changed"
    PRINT_JOB_FAILED = "print_job.failed"
    PRINT_JOB_COMPLETED = "print_job.completed"

    # ── Customers / orders / payments / custom orders ───────────────────
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_ARCHIVED = "customer.archived"
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_CANCELED = "order.canceled"
    ORDER_REFUNDED = "order.refunded"
    PAYMENT_RECORDED = "payment.recorded"
    PAYMENT_UPDATED = "payment.updated"
    PAYMENT_VOIDED = "payment.voided"
    PAYMENT_REFUNDED = "payment.refunded"
    CUSTOM_REQUEST_CREATED = "custom_request.created"
    CUSTOM_REQUEST_UPDATED = "custom_request.updated"
    CUSTOM_REQUEST_STATUS_CHANGED = "custom_request.status_changed"
    CUSTOM_REQUEST_CONVERTED = "custom_request.converted"

    # ── POS ─────────────────────────────────────────────────────────────
    POS_SESSION_OPENED = "pos_session.opened"
    POS_SESSION_CLOSED = "pos_session.closed"
    POS_SESSION_VOIDED = "pos_session.voided"
    POS_SALE_COMPLETED = "pos_sale.completed"
    POS_SALE_VOIDED = "pos_sale.voided"
    POS_SALE_REFUNDED = "pos_sale.refunded"

    # ── Markets ─────────────────────────────────────────────────────────
    MARKET_CREATED = "market.created"
    MARKET_UPDATED = "market.updated"
    MARKET_STATUS_CHANGED = "market.status_changed"
    MARKET_COMPLETED = "market.completed"
    MARKET_FINANCIAL_FIELDS_CHANGED = "market.financial_fields_changed"
    MARKET_PACKING_LIST_CREATED = "market_packing_list.created"
    MARKET_PACKING_LIST_UPDATED = "market_packing_list.updated"

    # ── Receipts / expenses ─────────────────────────────────────────────
    RECEIPT_UPLOADED = "receipt.uploaded"
    RECEIPT_EXTRACTED = "receipt.extracted"
    RECEIPT_PARSED_BY_AI = "receipt.parsed_by_ai"
    RECEIPT_MANUALLY_EDITED = "receipt.manually_edited"
    RECEIPT_APPROVED = "receipt.approved"
    RECEIPT_REJECTED = "receipt.rejected"
    RECEIPT_ARCHIVED = "receipt.archived"
    EXPENSE_LEDGER_CREATED = "expense_ledger.created"
    EXPENSE_LEDGER_UPDATED = "expense_ledger.updated"
    EXPENSE_LEDGER_DELETED = "expense_ledger.deleted"
    EXPENSE_LEDGER_ARCHIVED = "expense_ledger.archived"

    # ── Prep tasks ──────────────────────────────────────────────────────
    PREP_TASK_GENERATED = "prep_task.generated"
    PREP_TASK_UPDATED = "prep_task.updated"
    PREP_TASK_COMPLETED = "prep_task.completed"
    PREP_TASK_REOPENED = "prep_task.reopened"

    # ── Cost engine ─────────────────────────────────────────────────────
    COST_ENGINE_SNAPSHOT_RECORDED = "cost_engine.snapshot_recorded"

    # ── Analytics / AI ──────────────────────────────────────────────────
    ANALYTICS_AI_INSIGHT_GENERATED = "analytics.ai_insight_generated"

    # ── Imports / exports / uploads ─────────────────────────────────────
    CSV_IMPORTED = "csv.imported"
    CSV_EXPORTED = "csv.exported"
    FILE_UPLOADED = "file.uploaded"

    # ── Catch-all helpers (use sparingly) ───────────────────────────────
    ADMIN_ACTION = "admin.action"
    DESTRUCTIVE_ACTION = "admin.destructive_action"


# Convenience: the set of every action value. Useful for the coverage test.
ALL_ACTIONS: frozenset[str] = frozenset(a.value for a in AuditAction)


# Backward-compatible: services that already pass strings like
# ``"market_catalog.updated"`` continue to work because ``record_audit_event``
# does not validate. The coverage test just flags unrecognised values.
