# Gap Fix Results

Date: 2026-07-14

Comprehensive codebase review and fix pass covering the full DFPOS application at `/mnt/storage/docker/dfpos`.

---

## Overview

This document catalogs all bugs, gaps, incomplete features, configuration errors, and code-quality issues found during a thorough review of the entire codebase, along with the fixes applied and any remaining items that still need attention.

The review covered:
- All 28 SQLAlchemy model files
- All 27 Flask blueprints (routes, forms, schemas)
- All 54 service files
- All templates (Jinja2)
- All static assets (CSS, JS)
- Configuration (config.py, .env.example, pyproject.toml)
- Infrastructure (Dockerfile, docker-compose.yml, migrations)
- Tests (33 test files)
- Docs (26 markdown files)
- Microservices (audit-log, intelligence)
- Module registry, feature flags, theme system

---

## Critical Bugs (Fixed)

### 1. User Model Missing `business_id` Column

**File**: `app/models/user.py`

**Issue**: The `User` model did not define a `business_id` column, but the timezone utility at `app/utils/timezone.py:35` referenced `current_user.business_id`. This would cause `AttributeError` at runtime whenever `get_user_timezone()` was called for an authenticated user whose business has a timezone set.

**Fix**: Added `business_id` column to the `User` model with a proper `ForeignKey("businesses.id")` constraint and index. The column is nullable for backward compatibility.

```python
business_id: Mapped[int | None] = mapped_column(
    ForeignKey("businesses.id"), nullable=True, index=True
)
```

---

### 2. Migrations `env.py` Python 2 Syntax

**File**: `migrations/env.py:22`

**Issue**: Line 22 used Python 2 exception syntax `except TypeError, AttributeError:`. This is invalid in Python 3 and would cause Alembic migration commands to fail with a `SyntaxError`.

**Fix**: Changed to Python 3 syntax `except (TypeError, AttributeError):`.

---

### 3. Duplicate Keys in `BLUEPRINT_SECTION_MAP`

**File**: `app/__init__.py:273-301`

**Issue**: The `BLUEPRINT_SECTION_MAP` dictionary had duplicate keys:
- `"intelligence"` appeared at both lines 284 and 286 (the second entry overwrites the first silently)
- `"report_studio"` appeared at both lines 290 and 299 (same issue)

While Python accepts this silently, the last value wins, which makes the code misleading and suggests a copy-paste error.

**Fix**: Removed both duplicate entries, keeping only the first occurrence of each.

---

### 4. `AUDIT_LOG_FAIL_CLOSED` Config Confusion

**File**: `app/config.py:130-133`

**Issue**: The `AUDIT_LOG_FAIL_CLOSED` config variable used a complex fallback that conflated `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS` with `AUDIT_LOG_FAIL_CLOSED`:

```python
AUDIT_LOG_FAIL_CLOSED = _as_bool(
    os.getenv("AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS", os.getenv("AUDIT_LOG_FAIL_CLOSED")),
    False,
)
```

This means setting the env var `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS` controlled the `AUDIT_LOG_FAIL_CLOSED` config value, which is the opposite of what the naming suggests. There was no separate config for financial-action-specific fail-closed behavior.

**Fix**: Split into two separate config values:

```python
AUDIT_LOG_FAIL_CLOSED = _as_bool(os.getenv("AUDIT_LOG_FAIL_CLOSED"), False)
AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS = _as_bool(
    os.getenv("AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS"),
    AUDIT_LOG_FAIL_CLOSED,  # falls back to the general setting
)
```

---

### 5. Missing ForeignKey Constraints on Core Models

Five models had `Integer` columns acting as foreign keys without actual FK constraints, weakening referential integrity:

**Files fixed**:
| Model | Column | Former Type | Fixed Type |
|-------|--------|------------|------------|
| `Notification` | `user_id` | `Integer` | `ForeignKey("users.id")` |
| `Order` | `market_id` | `Integer` | `ForeignKey("markets.id")` |
| `Order` | `pos_session_id` | `Integer` | `ForeignKey("pos_sessions.id")` |
| `PosSession` | `market_id` | `Integer` | `ForeignKey("markets.id")` |
| `Expense` | `related_market_id` | `Integer` | `ForeignKey("markets.id")` |
| `Expense` | `related_order_id` | `Integer` | `ForeignKey("orders.id")` |
| `Expense` | `receipt_id` | `Integer` | `ForeignKey("receipts.id")` |

These ensure the database enforces referential integrity for these relationships.

---

### 6. Missing Content Security Policy (CSP) Header

**File**: `app/__init__.py:205-214`

**Issue**: The `register_security_headers` function set `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Strict-Transport-Security`, but did **not** set a `Content-Security-Policy` header. This left the application vulnerable to XSS attacks. Alpine.js and HTMX are loaded from CDN (`cdn.jsdelivr.net`, `unpkg.com`), which represents a supply-chain risk without CSP enforcement.

**Fix**: Added a comprehensive CSP header:

```
Content-Security-Policy: default-src 'self';
  script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com;
  style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com;
  img-src 'self' data: blob: https:;
  font-src 'self' https://fonts.gstatic.com;
  connect-src 'self' https://api.weather.gov;
  frame-ancestors 'none';
  form-action 'self';
  base-uri 'self'
```

---

## Moderate Issues (Fixed)

### 7. Duplicate / Stale ` 2` Files Removed

**Issue**: The codebase was polluted with 78+ stale duplicate files with a ` 2` suffix (e.g., `trend_scout_calibration 2.py`, `test_rate_limiting 2.py`, `_market_recommendations 2.html`). These appear to be artifacts from a file system or development tool that created backup copies. They confuse IDE navigation, code search, and could accidentally be imported by Python's module system.

**Fix**: Removed all duplicate ` 2` files from the entire repository, including:
- 8 app service/task files
- 7 template files  
- 4 test files
- 1 JS file
- 1 deploy script
- 3 documentation files
- 1 Playwright config
- 51 intelligence microservice files
- 1 test-results file

---

### 8. `.env.example` RECEIPT_OCR_PROVIDER Default Mismatch

**File**: `.env.example:38`

**Issue**: `.env.example` specified `RECEIPT_OCR_PROVIDER=tesseract` but `app/config.py:102` defaulted to `"paddleocr"`. This is a source of truth conflict.

**Fix**: Updated `.env.example` to match the code default: `RECEIPT_OCR_PROVIDER=paddleocr`.

---

### 9. `.env.example` AUDIT_LOG_ENABLED Default

**File**: `.env.example:71`

**Issue**: `AUDIT_LOG_ENABLED=false` in `.env.example` but the development workflow should have audit logging enabled for testing and debugging.

**Fix**: Changed to `AUDIT_LOG_ENABLED=true` so audit logging is active by default in development.

---

### 10. `Customer` Model Missing `business_id`

**File**: `app/models/customer.py`

**Issue**: The `Customer` model did not have a `business_id` foreign key, while all other core business models (Product, Order, Market, Expense, Receipt, PosSession, FeatureFlag) do. This is an inconsistency for the SaaS-later multi-tenant foundation.

**Status**: Not fixed in this pass. This requires a migration. See "Known Issues Not Addressed" below.

---

## Security Improvements (Fixed)

### 11. Content Security Policy

Added as described in Critical Bug #6. The CSP now:
- Restricts script sources to `'self'`, `'unsafe-inline'` (for Alpine.js), and CDN origins
- Restricts style sources similarly
- Blocks all frames (`frame-ancestors 'none'`)
- Restricts form submissions to same-origin
- Sets a strict `base-uri`

---

## Code Quality Issues (Fixed)

### 12. Duplicate Blueprint Keys in `BLUEPRINT_SECTION_MAP`

Fixed as described in Critical Bug #3.

---

## Known Issues Not Addressed

These items were identified but not fixed in this pass. They require discussion, schema migrations, or are scope-limited by design.

### High Priority

| Issue | File(s) | Why Not Fixed |
|-------|---------|---------------|
| `Customer` model missing `business_id` | `app/models/customer.py` | Requires migration; safe to do in next schema change |
| `PrintJob` model missing `business_id` | `app/models/print_job.py` | Same reason; needs migration |
| `FilamentSpool` model missing `business_id` | `app/models/inventory.py` | Same reason |
| `PrepTask` model missing `business_id` | `app/models/prep_task.py` | Same reason |
| `CustomRequest` model missing `business_id` | `app/models/custom_request.py` | Same reason |
| `Notification` model missing `business_id` | `app/models/notification.py` | Same reason |
| `InventoryRecord` model missing `business_id` | `app/models/inventory.py` | Same reason |
| In-memory rate limiting not suitable for multi-worker | `app/utils/rate_limit.py` | Needs Redis-backed solution; production concern |
| No database migration generated for model changes | `migrations/versions/` | Requires running database; document as next step |

### Medium Priority

| Issue | File(s) | Notes |
|-------|---------|-------|
| ~60% of required audit events not wired | Multiple services | AGENTS.md lists ~70+ audit events; ~30 are implemented. Requires systematic pass through all service files. |
| No Variant model | `app/models/` | Product options are flat on Product; AGENTS.md references variants. Would be a significant schema change. |
| No admin UI for editing Feature Flags | `app/blueprints/` | Feature flags exist in DB but no management UI. Requires new blueprint/route. |
| No CSP upgrade for `upgrade-insecure-requests` | `app/__init__.py` | Currently not set; useful for production with HTTPS. |
| `scripts/` directory is empty | `scripts/` | AGENTS.md mentions scripts/ as expected structure. |
| Hardcoded colors in public homepage template | `app/templates/public/home.html` | `rgba(255,164,116,0.22)` etc. should use CSS custom properties. Visual impact is minimal. |
| `Expense` model missing relationships | `app/models/expense.py` | Has FK columns but no SQLAlchemy `relationship()` definitions. Would need those added. |

### Low Priority

| Issue | File(s) | Notes |
|-------|---------|-------|
| No Redis-backed rate limiting | `app/utils/rate_limit.py` | Production concern; in-memory works for single-worker dev |
| No healthcheck for audit-log service | `docker-compose.yml` | The audit-log service has no health check unlike other services |
| `docker/mariadb/init/` directory may not exist | `docker-compose.yml:58` | Referenced in compose but might be missing; docker will create on first run |
| `POS_CARD_PROCESSOR` still `placeholder` | `.env.example` | Intentional; no card processing yet |
| No B2B/wholesale module | `app/` | Not required for current scope; AGENTS.md doesn't mandate it for initial build |
| Test suite requires MariaDB | `tests/conftest.py` | Cannot run tests in CI without DB; documented in scorecard |

---

## Remaining Audit Events Not Yet Wired

The following audit events from the AGENTS.md requirements are not yet dispatched (partial list):

- `product.created` / `product.updated` / `product.archived` / `product.restored`
- `variant.created` / `variant.updated` / `variant.archived` (no variant model exists)
- `filament_spool.created` / `filament_spool.updated` / `filament_spool.archived`
- `print_job.created` / `print_job.updated` / `print_job.status_changed` / `print_job.failed` / `print_job.completed`
- `customer.created` / `customer.updated` / `customer.archived`
- `custom_request.created` / `custom_request.updated` / `custom_request.status_changed` / `custom_request.converted`
- `order.created` / `order.updated` / `order.status_changed` / `order.canceled` / `order.refunded`
- `payment.recorded` / `payment.updated` / `payment.voided` / `payment.refunded`
- `expense_ledger.created` / `expense_ledger.updated` / `expense_ledger.deleted` / `expense_ledger.archived`
- `market.created` / `market.updated` / `market.status_changed` / `market.completed`
- `market_packing_list.created` / `market_packing_list.updated`
- `prep_task.generated` / `prep_task.updated` / `prep_task.completed` / `prep_task.reopened`
- `analytics_ai_insight.generated`
- `csv.import` / `csv.export`
- `file.upload`
- `admin.action`
- `destructive.action`

---

## Summary of Changes

| File | Change Type | Description |
|------|------------|-------------|
| `app/models/user.py` | Bug fix | Added missing `business_id` column with FK constraint |
| `migrations/env.py` | Bug fix | Fixed Python 2 `except` syntax to Python 3 |
| `app/__init__.py` | Bug fix | Removed duplicate keys in `BLUEPRINT_SECTION_MAP` |
| `app/__init__.py` | Security | Added Content-Security-Policy header |
| `app/config.py` | Bug fix | Split `AUDIT_LOG_FAIL_CLOSED` from `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS` |
| `app/models/notification.py` | Integrity | Changed `user_id` from plain `Integer` to `ForeignKey` |
| `app/models/order.py` | Integrity | Changed `market_id` and `pos_session_id` from `Integer` to `ForeignKey` |
| `app/models/pos.py` | Integrity | Changed `market_id` from `Integer` to `ForeignKey` |
| `app/models/expense.py` | Integrity | Changed `related_market_id`, `related_order_id`, `receipt_id` from `Integer` to `ForeignKey` |
| `.env.example` | Config | Fixed `RECEIPT_OCR_PROVIDER` default to match code |
| `.env.example` | Config | Changed `AUDIT_LOG_ENABLED` to `true` for development default |
| *(78 files)* | Cleanup | Removed stale ` 2` duplicate files across entire repo |

---

## Files Not Changed (But Should Be Reviewed)

- `app/models/customer.py` - Needs `business_id` column (requires migration)
- `app/models/print_job.py` - Needs `business_id` column (requires migration)
- `app/models/inventory.py` - FilamentSpool, InventoryRecord need `business_id` (requires migration)
- `app/models/prep_task.py` - Needs `business_id` column (requires migration)
- `app/models/custom_request.py` - Needs `business_id` column (requires migration)
- `app/models/notification.py` - Needs `business_id` column (requires migration)

---

## Second Pass Fixes (2026-07-14)

An additional deep pass was performed across all services, blueprints, forms, schemas, and models. The following additional issues were found and fixed:

### Critical Runtime Crashes Fixed

| # | Issue | File | Fix |
|---|-------|------|-----|
| 1 | `from app.services.cost_engine import get_cost_engine` — function does not exist | `app/services/report_studio.py:12` | Removed broken import (function was imported but never used) |
| 2 | `Product.is_active` column does not exist | `app/services/impulse_tray.py:112` | Changed to `Product.status == ProductStatus.ACTIVE` |
| 3 | `True` used as invalid SQL filter expression | `app/services/impulse_tray.py:111` | Changed to `Product.id.isnot(None)` |
| 4 | `client.get("forecast")` — relative URL instead of full forecast URL | `app/services/markets.py:318` | Changed to `client.get(fallback_url)` using the actual forecast URL from API response |
| 5 | `PrepTask` used in markets routes but never imported — would cause `NameError` | `app/blueprints/markets/routes.py:22-31` | Added `PrepTask` to imports |
| 6 | `customer.shipping_name`, `shipping_address_line_1` etc. don't exist on `Customer` model | `app/services/storefront.py:214-219` | Changed to use `Customer.address_line_1`, `.city`, `.state`, `.zip_code` fields; shipping info passed through to Order |
| 7 | `custom_request.name.split()` could crash on empty/None name | `app/services/orders.py:31-32` | Added defensive `.strip()` and fallback logic |
| 8 | Missing `ProductStatus` import in impulse_tray.py | `app/services/impulse_tray.py:9-23` | Added `ProductStatus` to imports |

### Model / Data Integrity Fixes

| # | Issue | File | Fix |
|---|-------|------|-----|
| 9 | Missing relationships on `InventoryMovement` (product, from_location, to_location) | `app/models/inventory_movement.py:46` | Added `product`, `from_location`, `to_location` relationship definitions |
| 10 | `Setting` model used old-style `db.Column()` annotations (only model in codebase) | `app/models/setting.py` | Modernized to `Mapped[] = mapped_column()` style |
| 11 | `Setting.type` column shadowed Python built-in `type()` | `app/models/setting.py:13` | Renamed attribute to `setting_type` with `mapped_column("type", ...)` to preserve DB column name |
| 12 | `Setting` model missing `from __future__ import annotations` | `app/models/setting.py` | Added import |
| 13 | `CostSnapshot` appears twice in `__all__` | `app/models/__init__.py:96,100` | Removed duplicate |
| 14 | `PrintFailureAutopsy` and enums not imported in `__init__.py` | `app/models/__init__.py` | Added imports and `__all__` entries |
| 15 | Missing FK on `PrintFailureAutopsy.model_asset_id` | `app/models/print_failure_autopsy.py:47` | Documented (no model_assets table exists yet) |

### Configuration / Security Fixes

| # | Issue | File | Fix |
|---|-------|------|-----|
| 16 | References to `setting.type` not updated after rename | `app/services/settings.py:56,69`, `app/blueprints/api/routes.py:1833`, `app/blueprints/settings/setting_routes.py:40,47` | All updated to `setting.setting_type` |
| 17 | `set_setting()` call in cost_engine used old `type=` kwarg | `app/blueprints/cost_engine/routes.py:38` | Changed to `setting_type=` |

### Missing Re-export Fixes

| # | Issue | File | Fix |
|---|-------|------|-----|
| 18 | Receipt schemas not re-exported from `app/schemas/__init__.py` | `app/schemas/__init__.py` | Added `ReceiptSchema`, `ReceiptLineItemSchema`, `ReceiptLineAllocationSchema`, `ReceiptDashboardSchema` |
| 19 | Receipt, Promotion, and TableLayout forms not re-exported from `app/forms/__init__.py` | `app/forms/__init__.py` | Added all missing form class imports and `__all__` entries |

### Issues Identified But Not Fixed (Requires Migration or Broader Work)

| # | Issue | Severity | Reason |
|---|-------|----------|--------|
| 20 | `TrendOpportunityScore.product_id` is plain `Integer` with no FK | Medium | Would require schema migration and depends on trend data model decisions |
| 21 | `PrintJob.trend_opportunity_id` is plain `Integer` with no FK | Medium | Would require schema migration |
| 22 | `ReceiptLineAllocation.market_id`, `custom_job_id`, `inventory_item_id` are plain `Integer` with no FK | Medium | Receipt allocations are denormalized by design |
| 23 | `ReceiptLineItem.category_id` is plain `Integer` with no FK | Low | Denormalized receipt data |
| 24 | `ReceiptLineAllocation.expense_category_id` is `Integer` but `ExpenseCategory` is a `StrEnum` | Medium | Would require schema migration to change column type |
| 25 | Missing indexes on `AMSUnit.status`, `AMSUnit.type`, `FilamentSpool.status` | Low | Performance issue, not correctness |
| 26 | Schema `load_default` missing on several non-nullable numeric fields (Order, PosSession, PosSale, InventoryRecord schemas) | Low | API endpoint handles defaults server-side; schema-level default would be defensive |
| 27 | `ReceiptReviewForm` monetary fields are `StringField` with no decimal validation | Low | `_parse_money()` handles conversion but silently returns None on failure |

---

## Next Recommended Steps

1. **Generate migration**: Run `flask db migrate -m "gap_fix_pass_2026_07_14"` against MariaDB to create the migration for all model changes.
2. **Run full test suite**: Execute `uv run pytest` against a local MariaDB to verify no regressions.
3. **Wire remaining audit events**: Prioritize financial and CRUD audit events (order, payment, expense, print job, customer).
4. **Add Feature Flag admin UI**: Create a blueprint/settings page for toggling FeatureFlags in the admin panel.
5. **Add Redis rate limiting**: Replace in-memory rate limiter with Redis-backed implementation for multi-worker production.
6. **Add business_id to remaining models**: Customer, PrintJob, FilamentSpool, InventoryRecord, PrepTask, CustomRequest, Notification in a single migration.
7. **Fix schema load_default omissions**: Add `load_default` to `OrderSchema`, `PosSessionSchema`, `PosSaleSchema`, `InventoryRecordSchema` non-nullable fields.
8. **Add form-level numeric validation**: Add proper `DecimalField` or validation to `ReceiptReviewForm`, `ExpenseForm`, and `MarketForm` monetary fields.
