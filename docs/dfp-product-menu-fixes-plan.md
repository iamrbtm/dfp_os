# Plan: DFP Product And Menu Fixes

**Generated**: 2026-08-01
**Estimated Complexity**: Medium

## Overview
This plan covers the exact fixes requested in this session: responsive public menu behavior, product deletion, product grouping/sorting, Product Studio list metadata, dynamic inventory readiness scoring, inventory-score visual borders, and SKU defaulting.

The approach is to keep changes small and targeted, use existing Flask/Jinja/Tailwind patterns, preserve historical transaction records where deletion could corrupt business history, and validate only the affected files/workflows.

## Prerequisites
- Existing Flask app and MariaDB schema are available.
- Product Studio remains the primary admin product editing surface.
- Product deletion is admin-only.
- Historical orders, POS sales, print jobs, and demand events should not be deleted just because a product is deleted; they should be unlinked where nullable.
- Product-owned files and product-owned setup records should be deleted with the product.

## Sprint 1: Responsive Menu
**Goal**: Make the public responsive menu open and close reliably on logged-out/public pages.

**Demo/Validation**:
- Open the public site at mobile width.
- Tap `Menu`; links appear.
- Tap `Close`; links disappear.
- Confirm the cart link and nav links still work.

### Task 1.1: Identify Public Menu Runtime Dependency
- **Location**: `app/templates/components/_header.html`, `app/templates/base.html`
- **Description**: Confirm whether the menu uses Alpine, vanilla JS, or HTMX and whether that dependency loads on public pages.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Root cause is documented in implementation notes or commit summary.
  - No unrelated menu rewrites are introduced.
- **Validation**:
  - Manual browser check at mobile width.

### Task 1.2: Load Required Menu Runtime On Public Pages
- **Location**: `app/templates/base.html`
- **Description**: Ensure Alpine is available for the public header since it uses `x-data`, `@click`, `:class`, and `x-text`.
- **Dependencies**: Task 1.1
- **Acceptance Criteria**:
  - Public menu toggle works for anonymous visitors.
  - Authenticated admin/sidebar behavior remains unchanged.
- **Validation**:
  - `uv run python -m py_compile app/blueprints/public/routes.py`
  - Manual mobile menu open/close check.

## Sprint 2: Product List Grouping And Studio Metadata
**Goal**: Improve product browsing in the public Shop and Product Studio lists.

**Demo/Validation**:
- Public Shop shows products grouped by category.
- Product Studio side list shows category groups sorted by category/name.
- Studio product cards show sale price, cost, margin, and visibility indicators.

### Task 2.1: Group Public Shop Products By Category
- **Location**: `app/blueprints/public/routes.py`, `app/templates/public/shop.html`, `app/static/src/css/app.css`
- **Description**: Query public products ordered by category name and product name, then pass grouped products to the Shop template.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Products are grouped by category.
  - Products inside each group are sorted by name.
  - Category and collection filters still work.
  - Search still records demand events with the same metadata.
- **Validation**:
  - Manual Shop page check with multiple categories.
  - Targeted syntax/lint on changed public files.

### Task 2.2: Group Product Studio Side List By Category
- **Location**: `app/blueprints/products/studio_routes.py`, `app/templates/products/studio.html`
- **Description**: Replace updated-at product ordering with category/name ordering for the Studio side list and render category group headings.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Products are grouped by category.
  - Products inside each group are sorted by name.
  - Current selected product remains visually identifiable.
- **Validation**:
  - Manual Product Studio check with multiple categories.
  - `uv run ruff check app/blueprints/products/studio_routes.py app/templates/products/studio.html` if template lint is available; otherwise targeted route lint plus manual render.

### Task 2.3: Add Studio Card Pricing And Visibility Metadata
- **Location**: `app/blueprints/products/studio_routes.py`, `app/templates/products/studio.html`
- **Description**: Add sale price, estimated cost, profit margin, and badges for public visibility, POS visibility, and featured state.
- **Dependencies**: Task 2.2
- **Acceptance Criteria**:
  - Sale price displays from `Product.base_price`.
  - Cost displays using available cost/profit fields without creating new schema.
  - Margin displays as a percentage where calculable and `n/a` where not.
  - Public/POS/featured indicators are visible without crowding the card.
- **Validation**:
  - Manual Product Studio side-list check.
  - Targeted route syntax/lint.

## Sprint 3: Inventory Readiness Scoring
**Goal**: Make Product Studio readiness inventory score use each product’s inventory threshold rules and show color-coded urgency.

**Demo/Validation**:
- Product with threshold `10` and stock `15+` shows `7/7` and green border.
- Product with threshold `10` and stock `11-14` shows `3.5/7` and yellow/orange border.
- Product with threshold `10` and stock `10 or less` shows `0/7` and red border.

### Task 3.1: Add Threshold-Based Inventory Readiness Helper
- **Location**: `app/services/product_ops.py`
- **Description**: Add a helper that calculates inventory score from total stock and total reorder threshold across product inventory records.
- **Dependencies**: None
- **Acceptance Criteria**:
  - `stock >= threshold * 1.5` returns `7`.
  - `stock > threshold and stock < threshold * 1.5` returns `3.5`.
  - `stock <= threshold` returns `0`.
  - Missing/zero threshold returns `0` with a clear reason.
- **Validation**:
  - Targeted unit test or direct service-level verification only for `product_ops` inventory scoring.

### Task 3.2: Wire Inventory Score Into Readiness Breakdown
- **Location**: `app/services/product_ops.py`, `app/templates/products/studio.html`
- **Description**: Replace the old inventory-on-hand boolean readiness check with the new partial-score logic.
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - Readiness breakdown can display `3.5/7`.
  - Total readiness score supports fractional inventory contribution when needed.
  - Existing launch gate behavior remains reasonable.
- **Validation**:
  - Manual Product Studio readiness check for the three threshold cases.
  - Targeted service test if available.

### Task 3.3: Add Inventory Score Border Colors To Studio Cards
- **Location**: `app/blueprints/products/studio_routes.py`, `app/templates/products/studio.html`
- **Description**: Compute inventory score per product card and render a left border color based on score.
- **Dependencies**: Task 3.1, Task 2.2
- **Acceptance Criteria**:
  - `7/7` uses success/green token.
  - `3.5/7` uses warning/yellow-orange token.
  - `0/7` uses danger/red token.
  - Uses design tokens, not hardcoded colors.
- **Validation**:
  - Manual Product Studio side-list check.

## Sprint 4: Product SKU Defaulting
**Goal**: If SKU is blank on save, copy the slug and force uppercase.

**Demo/Validation**:
- Create/edit a product with blank SKU.
- Save.
- Product SKU becomes the uppercase slug.

### Task 4.1: Generate Uppercase SKU During Form Validation
- **Location**: `app/forms/studio.py`
- **Description**: In `validate_sku_base`, generate an uppercase SKU from slug/name when the submitted SKU is blank, then run uniqueness checks against the generated value.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Blank SKU is not persisted as `None` when slug/name is available.
  - Explicit SKU is also normalized uppercase.
  - Duplicate generated SKU is still rejected.
- **Validation**:
  - Targeted form-level or Product Studio create/edit check only.

### Task 4.2: Persist Uppercase SKU In Product Population
- **Location**: `app/forms/studio.py`
- **Description**: Ensure `populate_product` persists uppercase SKU and falls back to uppercase product slug.
- **Dependencies**: Task 4.1
- **Acceptance Criteria**:
  - Saved product has uppercase SKU.
  - Existing nonblank SKU values are normalized uppercase on save.
- **Validation**:
  - Targeted form-level or Product Studio save check only.

## Sprint 5: Confirmed Product Deletion
**Goal**: Allow admins to delete products safely without making deletion too easy or corrupting historical business records.

**Demo/Validation**:
- Delete form appears away from the product name/list controls.
- Admin must type the product slug and confirm browser prompt.
- Product disappears after deletion.
- Product-owned files/records are removed.
- Historical order/POS/print-job rows are preserved but unlinked where nullable.

### Task 5.1: Define Product Deletion Policy
- **Location**: `app/blueprints/products/studio_routes.py`
- **Description**: Identify product-owned records versus historical transaction records. Delete owned records and unlink historical nullable references.
- **Dependencies**: None
- **Acceptance Criteria**:
  - Product-owned records are removed: images, model assets, analysis runs, cost snapshots, checklist items, photo shots, inventory records, packing-list rows, table placements, recommendations.
  - Historical records are unlinked, not deleted: order items, POS sale items, print jobs, demand events, promotion drafts/signs, failure autopsies, trend scores.
  - Product files are explicitly deleted from storage.
- **Validation**:
  - Code review of affected foreign keys.

### Task 5.2: Add Admin-Only Delete Route
- **Location**: `app/blueprints/products/studio_routes.py`
- **Description**: Add a `POST /products/studio/<id>/delete` route restricted to admins.
- **Dependencies**: Task 5.1
- **Acceptance Criteria**:
  - Staff cannot access the destructive endpoint.
  - Admin must submit matching product slug.
  - On mismatch, product is not deleted and user receives feedback.
  - On success, audit event is dispatched.
- **Validation**:
  - Manual route check or targeted route test only.

### Task 5.3: Add Delete UI With Confirmation
- **Location**: `app/templates/products/studio.html`
- **Description**: Add a dedicated danger-zone delete form below the retirement workflow, requiring typed slug plus browser confirmation.
- **Dependencies**: Task 5.2
- **Acceptance Criteria**:
  - Delete is not available as a list icon or one-click action.
  - Form clearly states permanent deletion and historical unlinking behavior.
  - CSRF protection is included.
- **Validation**:
  - Manual Product Studio check.

## Testing Strategy
- Do not run broad/unrelated test suites for this work unless explicitly requested.
- Run targeted lint/syntax checks for changed Python files:
  - `uv run ruff check app/blueprints/products/studio_routes.py app/blueprints/public/routes.py app/forms/studio.py app/services/product_ops.py`
  - `uv run python -m py_compile app/blueprints/products/studio_routes.py app/blueprints/public/routes.py app/forms/studio.py app/services/product_ops.py`
- Run only targeted workflow checks when requested:
  - Product Studio save with blank SKU.
  - Product Studio inventory score cases.
  - Product delete with wrong and correct slug.
  - Public Shop grouped category display.
  - Public mobile menu open/close.

## Potential Risks And Gotchas
- Product deletion can break if a new non-nullable `product_id` foreign key is added later and not included in the delete policy.
- Deleting uploaded files before database commit can leave files deleted if the database delete fails; this is acceptable for the current local product-management workflow but should be made transactional or queued if storage becomes remote/critical.
- If multiple inventory records exist for a product, this plan uses total stock and total threshold. If the desired behavior is per-location scoring, the helper should be adjusted.
- Fractional readiness scores may affect any code that assumes readiness score is an integer.
- Public Shop grouping changes SQL joins; filters should use relationship predicates to avoid duplicate joins.

## Rollback Plan
- Revert `app/templates/base.html` to authenticated-only Alpine loading if public menu is replaced with vanilla JS.
- Revert public Shop grouping by passing flat `products` and rendering one `product-grid`.
- Revert Product Studio list to `_load_products()` flat rendering if grouped cards cause layout issues.
- Disable product deletion by removing the delete route and form while leaving retirement workflow intact.
- Revert inventory readiness to boolean stock-on-hand if threshold scoring causes unexpected launch-gate behavior.
- Revert SKU generation by restoring blank SKU persistence if automatic SKU creation conflicts with existing catalog rules.
