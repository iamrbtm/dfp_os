# New Ideas Execution Report

## Program Start: 2026-07-11

This report is the authoritative implementation log for the New Ideas program (from `docs/New Ideas by Category.md`). It tracks milestones, phases, commits, tests, and production-readiness status.

---

## Milestone 1: Markets

Goal: Make market planning and post-market execution smarter, more complete, and more action-oriented.

Features:
- Market Application Tracker
- Post-Market Follow-Up Queue
- Table Layout Planner
- Impulse Tray Optimizer

### Phase 1.1: Market Application Tracker Foundation

**Status**: `done`

**Scope**: Add application-specific fields to the Market model, update forms/schemas, add migration, enhance admin UI with search/filter/sort, add API support, and wire audit events for create/update/status change/archive.

**Git status at start**: Only `docs/Ultimate New Ideas Execution Prompt.md` modified (pre-existing, unrelated).

**Files changed**:
- `app/models/market.py` — Added `application_deadline`, `application_url`, `application_contact`, `booth_rules`, `required_documents`, `follow_up_date`, `worth_repeating` fields.
- `app/forms/market.py` — Added fields to `MarketForm` and `MarketLogisticsForm` with apply() support.
- `app/schemas/market.py` — Added new fields to `MarketSchema`.
- `app/blueprints/markets/routes.py` — Added status filter support, application tracker columns, and sortable fields.
- `app/static/src/css/app.css` — Added `.app-filter-pill` and `.app-filter-pill-active` styles.
- `app/templates/dashboard/resource_list.html` — Added status filter pills for markets.
- `migrations/versions/c7c8d9e0f1a2_add_market_application_tracker_fields.py` — New migration for schema changes.
- `tests/test_phase5_markets_expenses.py` — Added tests: model creation, admin auth, status filter, admin create, API token enforcement.
- `docs/new_ideas_execution_report.md` — Updated.

**Checks run**:
- `python3 -m py_compile` — All Python files pass.
- `npm run build:css` — CSS rebuilt successfully.

**Commit hash**: `66e7b70`

**Risks**: MariaDB migration needs real DB test. CSRF handling in test forms skipped (disabled in test config).

**Next phase**: Phase 1.2 — Post-Market Follow-Up Queue


### Phase 1.2: Post-Market Follow-Up Queue

**Status**: `done`

**Scope**: Extend PrepTask with follow-up fields (follow_up_type, customer_id, linked records), create follow-up generation service, add admin queue view with complete/reopen/archive actions, wire audit events, add nav entry.

**Files changed**:
- `app/models/prep_task.py` — Added `FollowUpType` enum, 5 new fields to `PrepTask`.
- `app/models/__init__.py` — Exported `FollowUpType`.
- `app/services/follow_ups.py` — New service with `generate_market_follow_ups()`, `_gen_from_pos_sales()`, `_gen_from_custom_requests()`, `_gen_unpaid_deposits()`, `complete_follow_up()`, `reopen_follow_up()`, `archive_follow_up()`, `get_follow_up_queue()`.
- `app/blueprints/prep_tasks/routes.py` — Added `follow_up_queue()`, `follow_up_complete()`, `follow_up_reopen()`, `follow_up_archive()` routes.
- `app/blueprints/markets/routes.py` — Added `generate_follow_ups` endpoint.
- `app/module_registry.py` — Added Follow-Up Queue nav entry.
- `app/templates/dashboard/prep_tasks/follow_up_queue.html` — New template with search, market filter, status badges, complete/reopen/archive actions, pagination, empty state.
- `app/templates/markets/partials/_tasks_marketing.html` — Added "Generate Follow-Ups" button and "Follow-Up Queue" link.
- `migrations/versions/d1e2f3a4b5c6_add_follow_up_fields_to_prep_tasks.py` — New migration.
- `tests/test_phase5_markets_expenses.py` — Added 7 tests: queue auth, queue load, complete, reopen, archive, generate for completed, generate for pending, enum validation.

**Checks run**:
- `python3 -m py_compile` — All Python files pass.

**Commit hash**: `2de93ce`

### Phase 1.3: Table Layout Planner

**Status**: `done`

**Scope**: Product placement grid with table sections, inventory allocation per section, layout templates, photo snapshots, section management, and copy-from-template workflow.

**Files changed**:
- `app/models/table_layout.py` — New: `MarketTableLayout`, `MarketTableSection` (with `TableSectionType` enum), `MarketTablePlacement`.
- `app/models/__init__.py` — Exported new models.
- `app/forms/table_layout.py` — `MarketTableLayoutForm`, `MarketTableSectionForm`, `MarketTablePlacementForm`.
- `app/blueprints/table_layouts/` — New blueprint: layout CRUD, section add/delete, placement add/delete, archive, copy-from-template with default sections.
- `app/__init__.py` — Registered blueprint.
- `app/module_registry.py` — Registered module with admin nav entry.
- `app/templates/dashboard/table_layouts/list.html` — Card grid with photo previews.
- `app/templates/dashboard/table_layouts/form.html` — Create/edit with photo upload.
- `app/templates/dashboard/table_layouts/detail.html` — Section grid with inline product add, summary sidebar.
- `migrations/versions/e2f3a4b5c6d7_add_table_layout_models.py` — 3 new tables.
- `tests/test_phase5_markets_expenses.py` — Added 8 tests.

**Checks run**:
- `python3 -m py_compile` — All Python files pass.

**Commit hash**: `8617634`


### Phase 1.4: Impulse Tray Optimizer

**Status**: `done`

**Scope**: Analyze impulse tray product sell-through, generate rotation recommendations, and provide admin view with placement history.

**Files changed**:
- `app/services/impulse_tray.py` — Service with `get_impulse_tray_products()`, `get_impulse_tray_recommendations()`, `optimize_impulse_tray()`, `_calc_sell_through()`.
- `app/blueprints/prep_tasks/routes.py` — Added `impulse_tray_optimizer()` route.
- `app/module_registry.py` — Added Impulse Tray nav entry.
- `app/templates/dashboard/prep_tasks/impulse_tray.html` — Stats cards, rotation recommendations, placement history table.
- `tests/test_phase5_markets_expenses.py` — Added 4 tests.

**Checks run**:
- `python3 -m py_compile` — All Python files pass.

**Commit hash**: `1df4345`

**Next phase**: Milestone 2 — Promotion

---

## Milestone 2: Promotion

Goal: Turn product and market data into practical promotional assets without making unsupported business claims.

Features:
- Social Content Queue
- Market Display Sign Generator

### Phase 2.1: Promotion Module Foundation

**Status**: `done`

**Scope**: Models for content drafts and sign assets, status workflow, admin CRUD, API endpoints, module registry, permissions, audit logging, migration, and focused tests.

**Git status at start**: clean.

**Files changed**:
- `app/models/promotion.py` — New: `ContentDraft` (with `ContentStatus`, `ContentChannel` enums) and `SignAsset` (with `SignStatus` enum).
- `app/models/__init__.py` — Exported new models and enums.
- `app/forms/promotion.py` — `ContentDraftForm` and `SignAssetForm` with WTForms validation, apply(), and product/market/custom-request selectors.
- `app/schemas/promotion.py` — `ContentDraftSchema` and `SignAssetSchema` for API serialization.
- `app/services/promotion.py` — Service with draft generation from product/market/custom-request, approve/publish/archive, sign HTML generation, sign approve/archive.
- `app/blueprints/promotion/__init__.py` — Blueprint with `/promotion` prefix.
- `app/blueprints/promotion/routes.py` — Full CRUD for drafts and signs, approve/publish/archive flows, sign print view, generate-from-* endpoints, sign HTML regeneration.
- `app/module_registry.py` — Registered `promotion` module with nav entries.
- `app/__init__.py` — Registered blueprint, added BLUEPRINT_SECTION_MAP and CONTEXT_NAV_ITEMS for promotion.
- `app/templates/dashboard/promotion/draft_list.html` — Admin draft queue with status/channel filters.
- `app/templates/dashboard/promotion/draft_form.html` — Create/edit draft form.
- `app/templates/dashboard/promotion/draft_detail.html` — Draft detail with approve/publish/archive actions.
- `app/templates/dashboard/promotion/sign_list.html` — Admin sign list with status filters.
- `app/templates/dashboard/promotion/sign_form.html` — Create/edit sign form.
- `app/templates/dashboard/promotion/sign_detail.html` — Sign detail with preview and actions.
- `app/templates/dashboard/promotion/sign_print.html` — Print-optimized sign view with auto-print.
- `migrations/versions/e3f4a5b6c7d8_add_promotion_models.py` — New migration for `content_drafts` and `sign_assets` tables.
- `tests/test_promotion.py` — 20 tests: model creation, status enums, product links, draft generation from product/market/custom-request, approve/publish/archive workflow, sign HTML generation, sign approve/archive, missing product handling, auth enforcement, admin create flow, API token enforcement, audit dispatch.

**Checks run**:
- `python3 -m py_compile` — All Python files pass.

**Commit hash**: *(pending)*

**Risks**: MariaDB migration needs real DB test. Docker compose migration flow not verified in this session.

**Next phase**: Phase 2.2 — Social Content Queue
