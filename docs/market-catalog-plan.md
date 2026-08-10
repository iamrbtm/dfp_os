# Plan: Market Catalog / Discovery List

**Generated**: 2026-08-10
**Estimated Complexity**: Medium-High

## Overview

Build a **Market Catalog** — a master discovery pool of markets Dude Fish Printing *could* attend, kept up to date over time. Each catalog listing captures the full identity and logistics of a recurring market: location, organizer contact, dates/times, recurrence rules, categories, vendor/attendee counts, amenities (wifi, food, power), and multiple booth-size tiers with prices.

From the catalog, an admin hits **"Book it"** → opens a confirmation form pre-filled from the listing (next occurrence date computed from the recurrence rule, editable) → creates a dated **`Market`** instance (the existing booked-events module, unchanged in spirit) with all the right fields copied over, status `INTERESTED`/`APPLIED`, and a foreign key back to the catalog listing.

Recurrence is **full RRULE** via `python-dateutil` (already in `uv.lock`). The catalog supports "3rd Saturday in October", "every July 4th", multi-day festivals, and any other iCal RRULE. The system displays **this year + next year's** computed dates for planning. A scheduled job (or a request-time helper for v1) advances each listing's "current/next occurrence" once its date passes.

**Categories** are a user-editable table (`MarketCategory`) seeded with: Holiday, Flea, Craft, Farmers, Art, Antique/Vintage, Festival, Trade Show, Pop-up, Night Market, Other.

This plan does NOT alter the existing `Market` module's booked-event workflow (statuses, packing lists, weather, hotels, documents, prep tasks, performance). It only adds a `market_catalog_listing_id` FK + a copy-down `book_from_catalog` service.

### Prerequisites
- `python-dateutil` (provides `dateutil.rrule`) — already in `uv.lock`
- Existing `Market`, `MarketStatus`, markets blueprint/routes/services/forms/schemas/templates
- Alembic migrations chain (latest head: `c4d5e6f7a8b9`)
- Module registry + feature flags
- Audit-log microservice client

---

## Sprint 1: Data Model & Migration

**Goal**: New tables for catalog listings, categories, booth tiers, and the Market→Catalog FK.
**Demo/Validation**:
- `uv run flask --app app:create_app db upgrade` succeeds
- Tables exist with expected columns
- `Market` rows can reference a `MarketCatalogListing`

### Task 1.1: `MarketCategory` model
- **Location**: `app/models/market_catalog.py` (new file)
- **Description**: Editable category table. Columns: `id`, `name` (unique, indexed), `slug`, `description`, `sort_order`, `is_active`, `archived_at`, `created_at`, `updated_at`. Use `StrEnum`-free plain model since categories are user-editable. Add `slug` auto-derived in service layer.
- **Acceptance Criteria**:
  - Model defined with `PrimaryKeyMixin`, `TimestampMixin`, soft archive
  - Unique constraint on `name`
  - Index on `slug`, `is_active`
- **Validation**: import works; `MarketCategory(name=...)` constructs

### Task 1.2: `MarketCatalogListing` model
- **Location**: `app/models/market_catalog.py`
- **Description**: The discovery-pool master record. Captures the full identity of a market. Fields:
  - **Identity**: `name` (indexed), `slug`, `category_id` (FK→market_categories, indexed), `description`, `website_url`
  - **Location**: `location_name`, `address`, `city`, `state`, `zip_code`, `latitude`, `longitude`
  - **Timing**: `default_start_time`, `default_end_time`, `timezone` (default `America/Chicago`)
  - **Recurrence**: `rrule` (Text, nullable), `recurrence_description` (human-readable helper), `is_recurring` (Bool)
  - **Scale**: `estimated_vendor_count`, `estimated_attendee_count` (Integer, nullable)
  - **Amenities**: `power_available`, `wifi_available`, `food_available`, `restrooms_available`, `indoor`, `covered_outdoor`, `outdoor`, `parking_notes`
  - **Organizer contact**: `organizer_name`, `organizer_email`, `organizer_phone`, `application_url`, `application_contact`, `application_deadline_description`
  - **Rules/docs**: `booth_rules`, `required_documents`, `notes`
  - **Tracking**: `next_occurrence_date` (Date, nullable, indexed), `last_occurrence_date` (Date, nullable), `last_synced_at` (DateTime), `interest_level` (enum: WATCHING / INTERESTED / PRIORITY), `archived_at`
  - **Business**: `business_id` (FK→businesses, nullable, indexed)
- **Acceptance Criteria**:
  - All listed columns present with correct types
  - `Numeric` NOT used for non-money fields; integer counts use `Integer`
  - Indexes on name, slug, category_id, business_id, next_occurrence_date, interest_level
  - Relationships: `category`, `booth_tiers` (cascade delete-orphan), `booked_markets` (back to `Market`)
- **Validation**: Model constructs with defaults; `is_recurring=False` is valid (one-off discovered markets)

### Task 1.3: `MarketCatalogBoothTier` model
- **Location**: `app/models/market_catalog.py`
- **Description**: Child table — multiple booth size/price options per listing. Columns: `id`, `listing_id` (FK→market_catalog_listings, indexed), `label` (e.g. "10x10"), `dimensions` (e.g. "10ft x 10ft"), `price` (`Numeric(10,2)`), `corner_premium` (`Numeric(10,2)`, nullable — for markets that price "base + corner upcharge"), `notes`, `sort_order`, `created_at`, `updated_at`.
- **Acceptance Criteria**:
  - Money uses `Numeric(10,2)`, never `Float`
  - `sort_order` defaults to 0
  - Cascade delete with parent listing
- **Validation**: Can attach 3 tiers to one listing

### Task 1.4: Add FK to `Market`
- **Location**: `app/models/market.py`
- **Description**: Add `market_catalog_listing_id: Mapped[int | None]` FK→`market_catalog_listings.id`, nullable, indexed. Add `relationship("MarketCatalogListing", back_populates="booked_markets")`.
- **Acceptance Criteria**:
  - Nullable (existing booked markets remain valid without a listing)
  - Indexed for reverse lookup
- **Validation**: `Market(...).market_catalog_listing_id` exists

### Task 1.5: Register models in `app/models/__init__.py`
- **Location**: `app/models/__init__.py`
- **Description**: Export `MarketCategory`, `MarketCatalogListing`, `MarketCatalogBoothTier`, and `MarketInterestLevel` enum. Add to `__all__`.
- **Acceptance Criteria**: `from app.models import MarketCatalogListing` works
- **Validation**: Import succeeds

### Task 1.6: Migration
- **Location**: `migrations/versions/d5e6f7a8b9c0_market_catalog.py` (new)
- **Description**: Create tables `market_categories`, `market_catalog_listings`, `market_catalog_booth_tiers`, and add `market_catalog_listing_id` FK column + index to `markets`. `down_revision = "c4d5e6f7a8b9"`.
- **Acceptance Criteria**:
  - `upgrade()` creates 3 tables + 1 column + 1 index
  - `downgrade()` reverses cleanly
  - Seed default categories inside `upgrade()` via `op.bulk_insert`
- **Validation**: `uv run flask --app app:create_app db upgrade` then `db downgrade` both succeed on a clean DB

---

## Sprint 2: Recurrence Service

**Goal**: RRULE-based next-occurrence computation + listing sync.
**Demo/Validation**:
- Given an RRULE string, the service returns the next N occurrence dates
- "3rd Saturday of October yearly" and "July 4th yearly" both compute correctly for current + next year

### Task 2.1: `recurrence.py` service
- **Location**: `app/services/market_catalog/recurrence.py` (new package dir `app/services/market_catalog/`)
- **Description**: Pure functions wrapping `dateutil.rrule`. Include:
  - `parse_rrule(rrule_str) -> rrule.rrule | None`
  - `next_occurrences(rrule_obj, after_date, count=2) -> list[date]`
  - `next_occurrence(rrule_obj, after_date) -> date | None`
  - `build_rrule(frequency, month=None, day=None, weekday=None, week_number=None, interval=1) -> str` — helper to construct common RRULE strings from UI-friendly inputs
  - `humanize_rrule(rrule_str) -> str` — readable description ("3rd Saturday of October, annually")
  - `validate_rrule(rrule_str) -> tuple[bool, str | None]`
- **Acceptance Criteria**:
  - All functions pure, no DB access, no Flask context
  - Handles both `FREQ=YEARLY` (fixed date) and `FREQ=MONTHLY`/`FREQ=YEARLY` with `BYDAY`+`BYSETPOS` (nth weekday)
  - `after_date` defaults to today when None
- **Validation**: Unit tests in Sprint 6

### Task 2.2: Listing sync service
- **Location**: `app/services/market_catalog/sync.py`
- **Description**: `sync_listing_occurrences(listing, today=None, actor=None) -> bool` — if `is_recurring` and `rrule` set, compute next occurrence after `max(last_occurrence_date, today)`; if the stored `next_occurrence_date` is in the past, advance `next_occurrence_date` to the next future date and set `last_occurrence_date` to the old value. Audit `market_catalog.occurrence_advanced`. Returns True if changed.
- **Acceptance Criteria**:
  - Idempotent (running twice in same day = no change)
  - Never moves `next_occurrence_date` backwards
  - Logs audit event on change
- **Validation**: Unit test with a fake "today"

### Task 2.3: Bulk sync helper
- **Location**: `app/services/market_catalog/sync.py`
- **Description**: `sync_all_listings(actor=None)` — iterate all active recurring listings and call `sync_listing_occurrences`. Used by CLI and (later) a scheduled task.
- **Acceptance Criteria**: Skips archived and non-recurring listings
- **Validation**: CLI command in Sprint 5

---

## Sprint 3: Book-It Service & Catalog CRUD Service

**Goal**: Business logic for catalog management + the "Book it" flow that copies a listing into a `Market` instance.
**Demo/Validation**:
- `book_from_catalog(listing_id, event_date, booth_tier_id=None, actor=...)` returns a `Market` with all fields populated
- Catalog CRUD service methods create/update/archive with audit events

### Task 3.1: Catalog CRUD service
- **Location**: `app/services/market_catalog/catalog.py`
- **Description**: `create_listing`, `update_listing`, `archive_listing`, `restore_listing`, each dispatching audit events (`market_catalog.created/updated/archived/restored`). Handle slug generation, category validation, and booth-tier nested updates (replace tiers on update).
- **Acceptance Criteria**:
  - Audit `before_state`/`after_state` on updates
  - Booth tiers replaced atomically on listing update
  - Slug auto-generated from name, de-duplicated
- **Validation**: Unit test creates a listing with 2 tiers and reads it back

### Task 3.2: Category CRUD service
- **Location**: `app/services/market_catalog/catalog.py`
- **Description**: `create_category`, `update_category`, `archive_category` with audit events `market_category.*`.
- **Acceptance Criteria**: Name uniqueness enforced; slug auto-derived
- **Validation**: Unit test

### Task 3.3: `book_from_catalog` service ★
- **Location**: `app/services/market_catalog/booking.py`
- **Description**: `book_from_catalog(listing_id, event_date, booth_tier_id=None, status=MarketStatus.INTERESTED, actor=None) -> Market`. Copies listing fields into a new `Market`:
  - `name`, `location_name`, `address`, `city`, `state`, `zip_code`, `latitude`, `longitude`
  - `event_date` = supplied date
  - `start_time`, `end_time`
  - `power_available`, `wifi_available`, `food_available`
  - `application_url`, `application_contact`
  - `booth_rules`, `required_documents`
  - `booth_size` = selected tier's `label`/`dimensions` (or first tier if none selected)
  - `booth_fee` = selected tier's `price` (+ corner premium if a `corner_premium` field is later toggled at booking)
  - `application_fee` left blank (listing doesn't carry it)
  - `market_catalog_listing_id` = listing.id
  - `status` = supplied
  - Geocodes address if lat/long missing
  - Audit `market_catalog.booked` with listing_id + new market_id
- **Acceptance Criteria**:
  - All copyable fields populated; missing listing fields stay None (not zero)
  - Returns persisted `Market` with `id`
  - Audit event dispatched
  - Raises `ValueError` if listing archived or not found
- **Validation**: Unit test creates listing → books → asserts Market fields match

### Task 3.4: Next-occurrence helper for booking form
- **Location**: `app/services/market_catalog/booking.py`
- **Description**: `suggest_booking_dates(listing, today=None, count=4) -> list[date]` — returns the next few future occurrences for pre-populating the booking form's date picker. For non-recurring listings, returns the listing's `next_occurrence_date` if set, else empty.
- **Acceptance Criteria**: Respects archived state (returns []); respects `is_recurring=False`
- **Validation**: Unit test

---

## Sprint 4: Forms, Schemas, Admin UI, API

**Goal**: Admin pages for the catalog + categories + "Book it" button; API resources for both.
**Demo/Validation**:
- Admin can list/create/edit/archive catalog listings and categories
- "Book it" button opens a date-prefilled form and creates a Market
- API `/api/v1/market-catalog-listings` and `/api/v1/market-categories` work with token auth

### Task 4.1: Forms
- **Location**: `app/forms/market_catalog.py` (new)
- **Description**:
  - `MarketCategoryForm`: name, description, sort_order, is_active
  - `MarketCatalogListingForm`: all listing fields + `category_id` SelectField populated from active categories + `rrule` field (with a helper "build recurrence" sub-form: frequency, month, day-of-month, weekday, week-number — server-side composes RRULE on submit) + nested booth-tier entries (use `FieldList`/`FormField` for label/dimensions/price/corner_premium/notes)
  - `BookFromCatalogForm`: `listing_id` (hidden), `event_date` (DateField, required), `booth_tier_id` (SelectField of the listing's tiers), `status` (SelectField default INTERESTED), `apply_corner_premium` (BooleanField)
- **Acceptance Criteria**:
  - WTForms validation on all required fields
  - RRULE builder sub-form maps to/from RRULE string when present
  - Booth tiers editable inline (add/remove rows)
- **Validation**: Form renders; invalid input rejected

### Task 4.2: Schemas (Marshmallow)
- **Location**: `app/schemas/market_catalog.py` (new)
- **Description**: `MarketCategorySchema`, `MarketCatalogListingSchema` (including nested `booth_tiers` and `category`), `MarketCatalogBoothTierSchema`.
- **Acceptance Criteria**: Dump/load round-trip works; nested tiers serialize
- **Validation**: Schema dump test

### Task 4.3: Admin blueprint routes
- **Location**: `app/blueprints/market_catalog/` (new package — `__init__.py`, `routes.py`)
- **Description**: Follow the existing `markets` blueprint pattern (`ResourceConfig`, list/create/detail/edit/archive). Resources: `categories`, `listings`. Plus dedicated endpoints:
  - `GET /market-catalog/listings/<id>/book` → renders booking form pre-filled with suggested dates
  - `POST /market-catalog/listings/<id>/book` → calls `book_from_catalog`, redirects to `markets.detail_resource`
  - `POST /market-catalog/listings/<id>/sync` → forces occurrence sync for one listing (HTMX-friendly)
  - `GET /market-catalog/listings/<id>/occurrences` → returns next 4 occurrences as JSON (for the booking form date picker)
- **Acceptance Criteria**:
  - `roles_required(ADMIN, STAFF)` on all routes
  - Feature flag `module.market_catalog.enabled` enforced
  - "Book it" button on the catalog list and detail pages
- **Validation**: Manual click-through; automated test in Sprint 6

### Task 4.4: Templates
- **Location**: `app/templates/market_catalog/` (new: `list.html`, `detail.html`, `form.html`, `partials/_booking_modal.html`, `partials/_recurrence_builder.html`, `partials/_booth_tiers.html`)
- **Description**: Tailwind-based, follow `DESIGN.md` tokens. List page shows category pill filters, interest-level pills, next-occurrence column, "Book it" button per row. Detail page shows all fields, booth tier table, next 4 occurrences, organizer contact block, amenities pills, and a prominent "Book this market" CTA. Use existing dashboard `resource_list.html`/`resource_form.html` where they fit to stay consistent.
- **Acceptance Criteria**:
  - Empty states for no listings / no tiers / no recurrence
  - Loading + error states for the booking date picker (HTMX)
  - No hardcoded colors — design tokens only
- **Validation**: Visual review against DESIGN.md

### Task 4.5: Admin nav entries
- **Location**: `app/module_registry.py` (markets module or a new `market_catalog` module entry) + dashboard nav template
- **Description**: Add nav entries "Market Catalog" and (under it) "Categories" to the admin sidebar. Register the new blueprint. If using a new module, add `market_catalog` to the registry with `feature_flag_key="module.market_catalog.enabled"`, `default_enabled=True`, `dependencies=("markets",)`.
- **Acceptance Criteria**: Nav appears for ADMIN/STAFF; hidden when flag disabled
- **Validation**: Toggle flag → nav hidden + routes 403

### Task 4.6: API resources
- **Location**: `app/blueprints/api/routes.py`
- **Description**: Register `market-categories`, `market-catalog-listings`, `market-catalog-booth-tiers` in `API_RESOURCES`. Add `_apply_market_category`, `_apply_market_catalog_listing`, `_apply_market_catalog_booth_tier` functions. Add the resource→blueprint mapping for the new `market_catalog` blueprint.
- **Acceptance Criteria**:
  - Token-auth enforced
  - List/GET/POST/PUT/DELETE work
  - Feature flag enforced
- **Validation**: `curl` with token in Sprint 6

---

## Sprint 5: Seed Data, CLI, Module Wiring

**Goal**: Demo data, a sync CLI command, and full module/feature-flag wiring.
**Demo/Validation**:
- `flask seed demo` creates sample categories + 3-4 sample listings (incl. "3rd Saturday in October" and "July 4th")
- `flask market-catalog sync` advances stale occurrences

### Task 5.1: Seed data
- **Location**: `app/cli.py` (extend existing `seed_demo`)
- **Description**: Seed categories + sample listings:
  - Categories: Holiday, Flea, Craft, Farmers, Art, Antique/Vintage, Festival, Trade Show, Pop-up, Night Market, Other
  - Listings (clearly demo): "Clarksville Holiday Market" (FREQ=YEARLY BYMONTH=10 BYDAY=SA BYSETPOS=3 — 3rd Saturday October), "Liberty Day Festival" (FREQ=YEARLY BYMONTH=7 BYMONTHDAY=4 — July 4th), "Clarksville Flea Market" (monthly, 1st Sunday), "Riverside Craft Fair" (one-off, fixed date). Each with 2-3 booth tiers, organizer contact, amenities.
- **Acceptance Criteria**: Seed idempotent (skip if already present); demo data clearly flagged
- **Validation**: `flask seed demo` runs clean on fresh DB

### Task 5.2: CLI sync command
- **Location**: `app/cli.py`
- **Description**: `flask market-catalog sync` — calls `sync_all_listings`. Prints count of listings advanced.
- **Acceptance Criteria**: Works without external services; safe to run repeatedly
- **Validation**: Run twice, second run reports 0 advances

### Task 5.3: Module registry + feature flag defaults
- **Location**: `app/module_registry.py`, `app/config.py`, `.env.example`
- **Description**: Add `market_catalog` module definition (or extend `markets` module — decide based on Task 4.5). Add `MODULE_MARKET_CATALOG_ENABLED=true` default. Add to `.env.example`.
- **Acceptance Criteria**: Flag toggle disables routes + API + nav
- **Validation**: Test in Sprint 6

### Task 5.4: Audit event list update
- **Location**: `AGENTS.md` (audit events section) + `docs/`
- **Description**: Document new audit events: `market_category.created/updated/archived`, `market_catalog.created/updated/archived/restored/booked/occurrence_advanced`, `market_catalog_booth_tier.created/updated/deleted`.
- **Acceptance Criteria**: AGENTS.md updated
- **Validation**: Doc review

---

## Sprint 6: Tests

**Goal**: Pytest coverage for the new module.
**Demo/Validation**:
- `uv run pytest tests/test_market_catalog.py -v` passes

### Task 6.1: Recurrence unit tests
- **Location**: `tests/test_market_catalog_recurrence.py`
- **Description**: Test `next_occurrences` for: 3rd Saturday of October (yearly), July 4th (yearly), 1st Sunday monthly, one-off, invalid RRULE (returns None / raises cleanly).
- **Acceptance Criteria**: All assertions pass; covers current + next year
- **Validation**: `pytest`

### Task 6.2: Service tests
- **Location**: `tests/test_market_catalog.py`
- **Description**:
  - Catalog CRUD creates + updates + archives with audit dispatch mocked
  - `book_from_catalog` copies all expected fields; Market has `market_catalog_listing_id` set; audit dispatched
  - `sync_listing_occurrences` advances past `next_occurrence_date`; idempotent
  - Booking from archived listing raises
- **Acceptance Criteria**: Audit client mock asserts `record` called with expected `action`
- **Validation**: `pytest`

### Task 6.3: Route + API tests
- **Location**: `tests/test_market_catalog_routes.py`
- **Description**:
  - Catalog list page requires login
  - Create listing via admin form
  - "Book it" creates a Market and redirects
  - API `/api/v1/market-catalog-listings` requires token, returns data with token
  - Feature flag off → 403 on routes + API
- **Acceptance Criteria**: All pass; flag-off test asserts 403
- **Validation**: `pytest`

### Task 6.4: Lint + format + full suite
- **Location**: repo root
- **Description**: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v --tb=long`
- **Acceptance Criteria**: All green
- **Validation**: CI commands pass

---

## Testing Strategy
- **Unit**: recurrence helpers (pure functions), services (DB-backed with SQLite or the MariaDB test DB), audit mock
- **Integration**: blueprint routes + API with token auth + feature flag toggling
- **Regression**: ensure existing `markets` tests still pass (no change to `Market` workflow)
- **Manual**: visual review of admin pages, "Book it" flow, recurrence builder UI

## Potential Risks & Gotchas
- **RRULE edge cases**: "3rd Saturday of October" requires `BYDAY=SA;BYSETPOS=3;BYMONTH=10;FREQ=YEARLY`. Verify with `dateutil.rrule` that `BYSETPOS` works with `FREQ=YEARLY` + `BYMONTH` — it does, but test thoroughly. Timezone handling: compute occurrences as dates (not datetimes) to avoid TZ drift; apply `default_start_time`/`default_end_time` at booking time.
- **Recurrence builder UI**: mapping arbitrary RRULEs back to form fields is hard. v1 form should support the common cases (yearly fixed date, yearly nth-weekday-of-month, monthly nth-weekday, monthly fixed day). Show the raw RRULE string for power users and allow direct editing. Don't try to round-trip every possible RRULE through the builder.
- **`next_occurrence_date` staleness**: until a real scheduler exists, the date shown is only refreshed on (a) listing save, (b) manual "sync" click, (c) CLI `market-catalog sync`, (d) booking form load. Document this; a future task can add APScheduler/cron.
- **Booking field drift**: when `Market` gains new fields later, `book_from_catalog` must be updated to copy them. Keep the copy mapping in one place (`booking.py`) and add a test asserting every copyable field is set.
- **Category deletion**: don't hard-delete categories that have listings. Soft-archive only; keep FK valid. Listings keep their `category_id`; archived categories just don't appear in the picker.
- **Demo data honesty**: per AGENTS.md, demo listings must be clearly flagged. Use a `is_demo` flag or prefix names with "[Demo]".
- **Soft delete vs archive**: catalog listings use `archived_at` (consistent with AGENTS.md soft-delete guidance). Don't physically delete.
- **Existing `Market.booth_size` is a string**: the catalog tier has structured `label`+`dimensions`; when booking, store the tier's `label` (e.g. "10x10") in `Market.booth_size` for backward compatibility. Don't migrate `Market.booth_size` to an FK — out of scope.

## Rollback Plan
- `uv run flask --app app:create_app db downgrade` reverses the migration (drops new tables, removes `markets.market_catalog_listing_id`)
- Revert code changes via git
- No data loss to existing `Market` rows (FK is nullable, new tables are additive)

## File Inventory (new)
- `app/models/market_catalog.py`
- `app/services/market_catalog/__init__.py`
- `app/services/market_catalog/recurrence.py`
- `app/services/market_catalog/sync.py`
- `app/services/market_catalog/catalog.py`
- `app/services/market_catalog/booking.py`
- `app/forms/market_catalog.py`
- `app/schemas/market_catalog.py`
- `app/blueprints/market_catalog/__init__.py`
- `app/blueprints/market_catalog/routes.py`
- `app/templates/market_catalog/*.html`
- `migrations/versions/d5e6f7a8b9c0_market_catalog.py`
- `tests/test_market_catalog*.py`

## File Inventory (modified)
- `app/models/market.py` — add `market_catalog_listing_id` FK + relationship
- `app/models/__init__.py` — exports
- `app/module_registry.py` — new module + nav
- `app/config.py` — feature flag default
- `app/blueprints/api/routes.py` — 3 new API resources
- `app/cli.py` — seed + sync command
- `AGENTS.md` — audit events list
- `.env.example` — `MODULE_MARKET_CATALOG_ENABLED=true`