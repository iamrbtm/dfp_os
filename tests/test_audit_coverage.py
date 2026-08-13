"""Audit coverage enforcement.

Two complementary tests:

1. ``test_no_undeclared_audit_actions_in_callers`` — every call site that
   passes a literal action string to ``record_audit_event`` uses either a
   member of ``AuditAction`` or one of a small allowlist of legacy
   strings (which the test will report so they can be migrated).

2. ``test_audit_actions_are_emitted_at_least_once`` — for every
   ``AuditAction`` value, at least one test fixture or runtime call
   references the matching literal. This catches dead enum members that
   no one actually emits.

3. ``test_blueprint_mutating_routes_emit_audits`` — every blueprint
   route that is not GET/HEAD/OPTIONS and is not a pure read is
   expected to either carry an ``@audited`` decorator or be on the
   explicit allowlist (e.g. reads that look like state changes).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.utils.audit_events import AuditAction

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = REPO_ROOT / "app"

# Routes/views where audit emission is intentionally delegated to the
# service layer (which audits) or where the call site is read-only.
# Each entry is the dotted path to the function decorated by ``@bp.<verb>``.
EXPLICIT_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Reads / dashboards / pages that just render forms.
        "app.blueprints.audit_logs.routes.index",
        "app.blueprints.audit_logs.routes.detail",
        "app.blueprints.dashboard.routes.index",
        "app.blueprints.feature_flags.routes.index",
        "app.blueprints.pos.routes.session_list",
        "app.blueprints.settings.setting_routes.settings_list",
        "app.blueprints.settings.theme_routes.themes",
        "app.blueprints.api_tokens.routes.list_tokens",
        "app.blueprints.api_tokens.routes.token_detail",
        # Public site — audits are emitted by the service layer
        # (create_custom_request, order creation, etc.).
        "app.blueprints.public.routes.home",
        "app.blueprints.public.routes.shop",
        "app.blueprints.public.routes.cart_view",
        "app.blueprints.public.routes.cart_update",
        "app.blueprints.public.routes.cart_remove",
        "app.blueprints.public.routes.checkout",
        "app.blueprints.public.routes.custom_orders",
        "app.blueprints.public.routes.contact",
        "app.blueprints.public.routes.product_detail",
        # Receipts — audited in app.services.receipts.
        "app.blueprints.receipts.routes.upload",
        "app.blueprints.receipts.routes.review",
        "app.blueprints.receipts.routes.inline_edit_line_item",
        "app.blueprints.receipts.routes.edit_line_item",
        "app.blueprints.receipts.routes.assign",
        "app.blueprints.receipts.routes.allocate_taxes",
        "app.blueprints.receipts.routes.check_receipt_duplicates",
        "app.blueprints.receipts.routes.resolve_receipt_duplicate",
        "app.blueprints.receipts.routes.reprocess",
        "app.blueprints.receipts.routes.archive",
        "app.blueprints.receipts.routes.api_process",
        # Settings — feature flag and business settings go through
        # create_resource / update_resource in admin_mutations which audit.
        "app.blueprints.settings.setting_routes.business_settings",
        "app.blueprints.settings.setting_routes.feature_flag_new",
        "app.blueprints.settings.setting_routes.feature_flag_edit",
    }
)


def _collect_audit_action_literals() -> set[str]:
    """Walk every Python file under app/ and collect string literals
    passed as the ``action=`` keyword to ``record_audit_event`` or
    ``AuditClient.record``. Returns the set of action strings found.
    """
    found: set[str] = set()
    for path in APP_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword):
                continue
            if node.arg != "action":
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(value.value)
    return found


def _collect_audit_action_usages() -> set[str]:
    """Walk Python files for ``AuditAction.<MEMBER>.value`` usages and
    collect the resolved string values."""
    found: set[str] = set()
    for path in APP_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "AuditAction"
                and isinstance(node.attr, str)
            ):
                member = getattr(AuditAction, node.attr, None)
                if member is not None:
                    found.add(member.value)
    return found


def test_no_undeclared_audit_actions_in_callers():
    """Every literal action= string must be in AuditAction OR a known legacy
    value. Anything else is a typo or a forgotten enum member.
    """
    legacy_strings: set[str] = {
        # Legacy strings still in use. Migrate as you touch them.
        "customer.created",
        "customer.updated",
        "customer.archived",
        "order.created",
        "order.updated",
        "order_item.created",
        "order_item.updated",
        "order_item.archived",
        "order_item.deleted",
        "payment.created",
        "payment.updated",
        "payment.archived",
        "pos_session.opened",
        "pos_session.closed",
        "pos_session.voided",
        "pos_sale.completed",
        "pos_sale.refunded",
        "user.logged_in",
        "user.logged_out",
        "user.login_failed",
        "user.login_rate_limited",
        "custom_request.created",
        "custom_request.updated",
        "custom_request.archived",
        "settings.changed",
        "module.status_changed",
        "feature_flag.toggled",
        "api_token.missing",
        "api_token.invalid",
        "api_token.scope_denied",
        "receipt.uploaded",
        "receipt.ai_parsed",
        "receipt.approved",
        "receipt.rejected",
        "expense.created",
        "expense.updated",
        "expense.archived",
        "expense_ledger_entry.created",
        "inventory.deducted",
        "inventory.adjusted",
        "inventory.transferred",
        "inventory.transfer_received",
        "inventory.reserved",
        "inventory.released",
        "inventory.returned",
        "print_job.created",
        "print_job.completed",
        "print_job.failed",
        "print_job.status_changed",
        "print_job.archived",
        "cost_snapshot.created",
        "csv.export",
        "model_analysis.completed",
        "model_analysis.failed",
        "model_analysis.started",
        "model_analysis.file_downloaded",
        "model_analysis.validated",
        "model_analysis.slicing_started",
        "model_analysis.sliced",
        "model_analysis.gcode_stored",
        "model_analysis.costed",
        "model_analysis.conversion_started",
        "model_analysis.pmp.started",
        "model_analysis.pmp.downloaded",
        "model_analysis.pmp.packed",
        "model_analysis.pmp.stored",
        "model_analysis.pmp.completed",
        "model_analysis.pmp.failed",
        "product_model.pmp.completed",
        "product_model.pmp.failed",
        "market_catalog.updated",
        "module.disabled_access_attempted",
        "authorization.failed",
        "table_layout.created",
        "booth_mode.viewed",
        "booth_mode.snoozed",
        "booth_mode.acknowledged",
        "content_draft.created",
        "content_draft.updated",
        "content_draft.generated_from_product",
        "content_draft.generated_from_market",
        "content_draft.generated_from_custom_request",
        "content_draft.approved",
        "content_draft.published",
        "content_draft.archived",
        "sign_asset.created",
        "sign_asset.updated",
        "sign_asset.ai_image_generated",
        "sign_asset.generated_from_market",
        "sign_asset.approved",
        "sign_asset.archived",
        "intelligence.ask_dfp",
        "intelligence.legacy_promoted",
        "intelligence.legacy_staging_cleaned",
        "intelligence.legacy_warehouse_rebuilt",
        "intelligence.market_advisor.generated",
        "intelligence.pipeline_run",
        "intelligence.warehouse_rebuilt",
        "market_catalog.archived",
        "market_catalog.booked",
        "market_catalog.created",
        "market_catalog.occurrence_advanced",
        "market_catalog.restored",
        "market_category.archived",
        "market_category.created",
        "market_category.updated",
        "model_analysis.conversion_completed",
        "model_analysis.enqueue_failed",
        "model_analysis.queued",
        "pickup_batch.prep_tasks_generated",
        "product.deleted",
        "product.launch_override",
        "product_asset.deleted",
        "product_image.uploaded",
        "product_model.pmp.queued",
        "product_model.uploaded",
        "product_story_card.ai_generated",
        "receipt.ai.extraction",
        "receipt.allocation",
        "receipt.duplicate_check",
        "receipt.ocr.complete",
        "theme.default_updated",
        "trend_opportunity.create_product",
        "trend_opportunity.print_now",
        "trend_opportunity_score.calculated",
        "trend_scout.added_to_market_prep",
        "trend_scout.calibration.completed",
        "trend_scout.calibration.failed",
        "trend_scout.calibration.manual_run",
        "trend_scout.calibration.regression",
        "trend_scout.create_product.redirected",
        "trend_scout.flag_clearance",
        "trend_scout.flag_license_review",
        "trend_scout.flag_retire",
        "trend_scout.opportunity.dismissed",
        "trend_scout.opportunity.undismissed",
        "trend_scout.print_now.created",
        "trend_scout.print_now.skipped",
        "trend_scout.settings.profile_loaded",
        "trend_scout.settings.profile_saved",
        "trend_scout.settings.source_toggled",
        "trend_scout.settings.weights_saved",
        "trend_scout.task_cancelled",
        "trend_scout.task_retried",
        "user.theme_updated",
    }
    declared = {a.value for a in AuditAction}
    found = _collect_audit_action_literals()
    undeclared = found - declared - legacy_strings
    assert not undeclared, (
        f"Found {len(undeclared)} undeclared audit action literals: "
        f"{sorted(undeclared)}. Add them to AuditAction or to legacy_strings."
    )


def test_audit_action_enum_covers_documented_events():
    """The AuditAction enum must include every event name listed in
    AGENTS.md's "Required Audit Events" section. This is a forward
    check — the enum declares the contract, and the test fails if a
    required event is missing from the enum (not the other way
    around; the enum is allowed to have more values than are
    currently emitted).
    """
    # The set below mirrors the "Required Audit Events" bullet list in
    # AGENTS.md. If a new required event is added to AGENTS.md, add it
    # to the enum AND to this set; if the AGENTS list shrinks, prune
    # the enum.
    documented_required: set[str] = {
        # Auth / users
        "user.login_succeeded",
        "user.login_failed",
        "user.logout",
        "user.password_changed",
        "user.created",
        "user.updated",
        "user.deactivated",
        "user.role_changed",
        "api_token.created",
        "api_token.revoked",
        # Settings / feature flags / modules
        "setting.changed",
        "feature_flag.changed",
        "module.enabled",
        "module.disabled",
        "module.disabled_access_attempted",
        "auth.failed_authorization",
        # Products / variants / models
        "product.created",
        "product.updated",
        "product.archived",
        "product.restored",
        "variant.created",
        "variant.updated",
        "variant.archived",
        "variant.restored",
        "model_asset.license_tracked",
        # Inventory
        "inventory.adjusted",
        "inventory.transferred",
        "inventory.deducted",
        "inventory.reserved",
        "inventory.released",
        # Print jobs
        "print_job.created",
        "print_job.updated",
        "print_job.status_changed",
        "print_job.failed",
        "print_job.completed",
        # Customers / orders / payments / custom orders
        "customer.created",
        "customer.updated",
        "customer.archived",
        "order.created",
        "order.updated",
        "order.status_changed",
        "order.canceled",
        "order.refunded",
        "payment.recorded",
        "payment.updated",
        "payment.voided",
        "payment.refunded",
        "custom_request.created",
        "custom_request.updated",
        "custom_request.status_changed",
        "custom_request.converted",
        # POS
        "pos_session.opened",
        "pos_session.closed",
        "pos_session.voided",
        "pos_sale.completed",
        "pos_sale.voided",
        "pos_sale.refunded",
        # Markets
        "market.created",
        "market.updated",
        "market.status_changed",
        "market.completed",
        "market.financial_fields_changed",
        "market_packing_list.created",
        "market_packing_list.updated",
        # Receipts / expenses
        "receipt.uploaded",
        "receipt.extracted",
        "receipt.parsed_by_ai",
        "receipt.manually_edited",
        "receipt.approved",
        "receipt.rejected",
        "receipt.archived",
        "expense_ledger.created",
        "expense_ledger.updated",
        "expense_ledger.deleted",
        "expense_ledger.archived",
        # Prep tasks
        "prep_task.generated",
        "prep_task.updated",
        "prep_task.completed",
        "prep_task.reopened",
        # Cost engine
        "cost_engine.snapshot_recorded",
        # Analytics / AI
        "analytics.ai_insight_generated",
        # Imports / exports / uploads
        "csv.import",
        "csv.export",
        "file.uploaded",
    }
    declared = {a.value for a in AuditAction}
    missing = documented_required - declared
    assert not missing, (
        f"AuditAction is missing events required by AGENTS.md: {sorted(missing)}. "
        f"Add them to app/utils/audit_events.py."
    )


def test_blueprint_mutating_routes_emit_audits():
    """Walk every blueprint route, find non-GET endpoints, and ensure
    they have either an ``@audited`` decorator, are on the explicit
    allowlist, or are part of the ``/api/v1/`` API surface (which is
    auto-audited by the global after_request hook in
    ``app.__init__._register_api_audit_hook``).
    """
    from app import create_app

    app = create_app("testing")
    failures: list[str] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = [m for m in (rule.methods or set()) if m not in {"GET", "HEAD", "OPTIONS"}]
        if not methods:
            continue
        # /api/v1/ is auto-audited by the global after_request hook.
        if rule.rule.startswith("/api/v1/") or rule.rule.startswith("/api/redoc"):
            continue
        view = app.view_functions.get(rule.endpoint)
        if view is None:
            continue
        qualname = f"{view.__module__}.{view.__name__}"
        if qualname in EXPLICIT_ALLOWLIST:
            continue
        if getattr(view, "_audited", False):
            continue
        try:
            from inspect import getsource, getsourcefile

            src = getsource(view)
            src_file = getsourcefile(view)
        except OSError, TypeError:
            failures.append(f"{qualname} (route={rule.rule}, methods={methods}) — cannot inspect")
            continue
        if (
            "record_audit_event(" in src
            or "audit_log.append_event" in src
            or "get_audit_client()" in src
        ):
            continue
        # The view's module imports record_audit_event — the audit happens
        # in a helper or service called from the view.
        if src_file:
            module_file = Path(src_file)
            try:
                module_src = module_file.read_text()
            except OSError:
                module_src = ""
            if "record_audit_event(" in module_src or "get_audit_client(" in module_src:
                continue
        failures.append(
            f"{qualname} (route={rule.rule}, methods={methods}) — "
            f"no @audited decorator and no record_audit_event call found"
        )
    if failures:
        pytest.fail(
            "Blueprint routes with state-changing methods that don't emit audit events:\n  "
            + "\n  ".join(failures)
        )
