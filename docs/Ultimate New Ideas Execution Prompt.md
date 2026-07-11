# Ultimate New Ideas Execution Prompt

Use this prompt to drive a production-ready implementation of the feature set in `docs/New Ideas by Category.md`.

## Role

You are an AI implementation agent working in `/Users/rbtm2006/Documents/Projects/dfp_os`.

Your job is to convert the categorized idea list into production-ready DFPos features. Treat each category as a milestone. Within each milestone, break the work into small, shippable phases. At the end of every phase, commit the completed, verified work to git. Push only after an entire milestone is complete and verified.

The work is complete only when the implemented features are production-ready, fully wired into the app, tested, documented, audited, permissioned, and consistent with the DFPos design system.

## Required Read Order

Before planning or coding, read these files in order:

1. `AGENTS.md`
2. `PROMPTS.md`
3. `TODO.md`
4. `DESIGN.md`
5. `ARCHITECTURE.md`
6. `docs/New Ideas by Category.md`
7. `docs/production_readiness_scorecard.md`
8. Relevant models, routes, services, forms, schemas, migrations, templates, tests, and static assets for the current milestone.

Do not rely only on this prompt. Verify the actual code before making decisions.

## Global Rules

- Keep DFPos Flask-first, server-rendered, and production-minded.
- Use MariaDB, SQLAlchemy ORM, Flask-Migrate/Alembic, Flask-WTF, Marshmallow schemas, Tailwind, Jinja, HTMX where useful, and vanilla JavaScript.
- Do not introduce a separate Node backend or SPA architecture.
- Use design tokens from `DESIGN.md`; do not hardcode colors.
- Keep routes thin and business logic in services.
- Put browser validation in forms.
- Put API validation and serialization in schemas.
- Add migrations for persistent schema changes.
- Add API endpoints under `/api/v1/` where the feature should be externally accessible or used by internal async/dynamic UI.
- Add feature-flag/module-registry entries where a new module or meaningful submodule is introduced.
- Add permission enforcement and server-side feature flag enforcement.
- Add audit logging for meaningful actions.
- Do not create fake business claims, fake testimonials, fake analytics, fake sales, or fake policies.
- Demo data is allowed only when clearly marked as demo.
- Do not store card data.
- Do not commit secrets, `.env`, real credentials, API keys, or production tokens.
- Keep `TODO.md` updated as the live execution ledger.

## Git Cadence

At the start of each phase:

1. Run `git status --short`.
2. Identify unrelated dirty files and do not touch or revert them.
3. Update `TODO.md` to mark the phase as in progress.

At the end of each phase:

1. Run targeted formatting/checks/tests for the phase.
2. Update `TODO.md` with completed work and remaining gaps.
3. Run `git status --short`.
4. Stage only files relevant to that phase.
5. Commit with a clear message, for example:

```bash
git add <phase files>
git commit -m "Add market follow-up foundation"
```

At the end of each milestone:

1. Run the full relevant milestone test suite.
2. Run broader checks if feasible: `uv run pytest`, API/OpenAPI tests, migrations, and focused browser checks where UI-heavy.
3. Update docs and `docs/production_readiness_scorecard.md`.
4. Commit any final milestone documentation or hardening changes.
5. Push the branch only after the full milestone is complete:

```bash
git push origin HEAD
```

If push fails due to network/DNS/auth, leave the commits local, report the exact failure, and do not invent a successful push.

## Definition Of Production Ready

A phase is not done unless all applicable items are complete:

- Models and migrations exist for persistent data.
- Forms validate browser input.
- Schemas validate API input/output.
- Services own business logic.
- Admin/operator UI exists where needed.
- Public UI exists where customer-facing.
- API endpoints exist where useful.
- Feature flags and module registry entries are added where appropriate.
- Permission checks are enforced server-side.
- Audit events are dispatched for meaningful create/update/delete/approval/completion actions.
- Empty, loading, success, validation, and error states exist where relevant.
- Tests cover service behavior and critical route/API behavior.
- Migrations run.
- The UI follows `DESIGN.md`.
- Docs and `TODO.md` are updated.
- No secrets are committed.
- Existing user changes are not reverted.

A milestone is not complete until all phases in that category meet this bar and the milestone has been pushed.

## Cross-Cutting Architecture To Reuse

Prefer extending existing surfaces before creating new ones:

- Markets: `app/models/market.py`, `app/services/markets.py`, `app/blueprints/markets/routes.py`
- Products: `app/models/catalog.py`, Product Studio routes/templates, `app/services/cost_engine.py`, Trend Scout scoring
- Promotion: public/product templates, product assets, storage helpers, existing static build
- Report Studio: analytics services, Intelligence service summaries, Chart.js, API endpoints
- Printers: `app/models/fleet.py`, `app/models/print_job.py`, `app/services/model_analysis.py`, analytics printing summaries
- Orders/custom orders: `app/models/order.py`, `app/models/custom_request.py`, POS/order/custom-order services
- Booth Mode: POS sessions, market command center, market packing lists, analytics, cost engine
- Audit: `app/services/audit_client.py`, `app/services/audit.py`, audited mutation helpers
- API: `app/blueprints/api/routes.py`
- Feature flags/modules: `app/module_registry.py`, settings feature flag UI

## Milestone 1: Markets

Goal: Make market planning and post-market execution smarter, more complete, and more action-oriented.

Features:

- Post-Market Follow-Up Queue
- Market Application Tracker
- Table Layout Planner
- Impulse Tray Optimizer

### Phase 1.1: Market Application Tracker Foundation

Implement:

- Data model for market applications or extend `Market` cleanly if the existing model is sufficient.
- Fields for application deadline, fee, required documents, application URL/contact, booth rules, decision status, follow-up date, and repeat notes.
- Admin list/detail/create/edit flows.
- Search, filters, status pills, and sortable deadline/date columns.
- API endpoints for CRUD and filtering.
- Feature flag/module wiring if needed.
- Audit events for create/update/status change/archive.

Production checks:

- Migration runs.
- Tests cover model creation, admin auth, API token enforcement, and status changes.
- Empty states for no applications.

Commit after this phase.

### Phase 1.2: Post-Market Follow-Up Queue

Implement:

- Follow-up task model or reuse/extend `PrepTask` if that is the cleanest fit.
- Follow-up types: custom lead, requested color/product, unpaid deposit, pickup reminder, thank-you, quote follow-up.
- Automatic follow-up suggestions after market completion from POS sales, custom requests, market notes, and unpaid deposits.
- Admin queue view with due dates, owner, status, completion, reopen, and archive.
- Links back to market, customer, order, custom request, and POS sale where available.
- Audit events for generated, completed, reopened, and archived follow-ups.

Production checks:

- Tests cover generation from market data and completion.
- UI handles no leads and no market data.
- Permissions distinguish admin/staff/helper appropriately.

Commit after this phase.

### Phase 1.3: Table Layout Planner

Implement:

- Market table layout records with versioned layout JSON.
- Predefined layout objects: table, tray, sign, checkout area, product zone, impulse zone, premium zone.
- Admin UI for creating/editing a market layout.
- Simple drag/drop interface using lightweight vanilla JS or a small focused library if already acceptable in the project.
- Snapshot selected layout onto a completed market and allow notes about what worked.
- Store layout outcome notes for future reporting.

Production checks:

- Validate layout JSON server-side.
- Test create/update/load paths.
- Ensure mobile/tablet usability.
- No heavy SPA.

Commit after this phase.

### Phase 1.4: Impulse Tray Optimizer

Implement:

- Service that ranks low-cost impulse products using price, margin, print time, sales velocity, inventory, trend score, and market fit.
- Suggested tray quantity and refill quantity.
- Integration into market command center and packing list.
- One-click add to packing list or prep tasks.
- Explainable score breakdown.

Production checks:

- Tests cover ranking and quantity suggestions.
- Handles products with missing cost data.
- Uses Decimal, not floats, for money.

Commit after this phase.

### Milestone 1 Completion Gate

- Run market, prep task, inventory, API, and analytics tests relevant to this milestone.
- Run migration upgrade against the configured development DB.
- Update `docs/production_readiness_scorecard.md`.
- Push only after every Markets phase is committed and verified.

## Milestone 2: Promotion

Goal: Turn product and market data into practical promotional assets without making unsupported business claims.

Features:

- Social Content Queue
- Market Display Sign Generator

### Phase 2.1: Promotion Module Foundation

Implement:

- Promotion module registry entry if warranted.
- Models for content drafts and generated/sign assets.
- Status workflow: draft, needs_review, approved, published/used, archived.
- Admin list/detail/create/edit flows.
- API endpoints for content drafts and sign assets.
- Permissions and audit logging.

Production checks:

- Tests for model/service/API permissions.
- Feature flag enforcement.

Commit after this phase.

### Phase 2.2: Social Content Queue

Implement:

- Draft content queue sourced from products, markets, custom orders, booth photos/notes, and product story cards when available.
- Manual draft creation.
- AI-assisted draft creation only if AI is enabled and optional; otherwise deterministic/manual templates.
- Required human approval before marking content as published.
- Fields for channel, caption, media reference, product/market/custom-order links, planned publish date, and notes.
- No automatic posting in this phase unless explicitly requested later.

Production checks:

- Tests cover AI-disabled fallback.
- Audit draft creation/approval/archive.
- UI labels drafts clearly; no fake claims or fake customer stories.

Commit after this phase.

### Phase 2.3: Market Display Sign Generator

Implement:

- Generate printable signs for products, collections, custom order intake, pickup instructions, and market QR links.
- Include product name, price, short description, care note, QR code, and optional public URL.
- Use server-rendered HTML print view first; PDF export may be added if reliable.
- Use existing product images/storage references.
- Provide admin preview and print layout.

Production checks:

- Tests cover sign creation and URL/QR generation.
- Visual check for print-friendly layout.
- No unsupported claims or fake policies.

Commit after this phase.

### Milestone 2 Completion Gate

- Run promotion, product, public route, and API tests.
- Verify generated signs render correctly.
- Update docs and scorecard.
- Push only after the full Promotion milestone is production-ready.

## Milestone 3: Report Studio

Goal: Build a new centralized reporting area where the owner can access operational and strategic reports in one place.

Report Studio is a brand new category. It should feel like a first-class DFPos module, not a loose analytics page.

Features:

- Report Studio home
- Vendor Market Heat Map
- Market Application Tracker Report

### Phase 3.1: Report Studio Module Foundation

Implement:

- New `report_studio` module definition in `app/module_registry.py`.
- Blueprint under `app/blueprints/report_studio/`.
- Templates under `app/templates/report_studio/`.
- Service layer under `app/services/report_studio.py` or a package if needed.
- API endpoints under `/api/v1/report-studio/...`.
- Admin nav entry.
- Feature flag and permission enforcement.
- Report catalog model only if saved report state, saved filters, exports, or scheduled reports require persistence.

Production checks:

- Tests cover route auth, feature flag blocking, API token access, and empty states.
- UI follows `DESIGN.md` and is denser than marketing pages.

Commit after this phase.

### Phase 3.2: Report Studio Home

Implement:

- Central report index grouped by category: Markets, Products, Inventory, POS, Orders, Receipts, Printers, Promotion.
- Each report card shows purpose, last updated, required data health, export availability, and owner action.
- Include quick filters for date range, market, product category, channel, and report status where useful.
- Add data quality warnings: missing costs, missing market coordinates, no completed markets, incomplete receipt allocation, stale Intelligence sync.

Production checks:

- Tests cover data quality summaries.
- Empty state explains what data is needed.

Commit after this phase.

### Phase 3.3: Vendor Market Heat Map

Implement:

- Report that maps markets by profit, distance, booth fee, weather risk, traffic, repeat quality, and application status.
- Use existing market latitude/longitude when available.
- Provide non-map fallback table if coordinates are missing.
- Add filters by date range, status, city/state, repeat recommendation, and minimum profit.
- Include export to CSV.
- Do not rely on external map APIs unless keys/config and graceful fallback are implemented.

Production checks:

- Tests cover report data service, missing coordinates, CSV export, and permissions.
- No hardcoded external API keys.

Commit after this phase.

### Phase 3.4: Market Application Tracker Report

Implement:

- Report built from the Market Application Tracker.
- Show application pipeline, deadlines, expected costs, status counts, upcoming due dates, missing documents, and repeat/apply-again notes.
- Add summary metrics: applications due soon, fees at risk, accepted markets, rejected/waitlisted markets, and markets needing follow-up.
- CSV export.

Production checks:

- Tests cover pipeline calculations and export.
- Links drill back to market/application detail pages.

Commit after this phase.

### Milestone 3 Completion Gate

- Run report-studio, market, API, and OpenAPI tests.
- Verify feature flag behavior.
- Update `docs/production_readiness_scorecard.md`.
- Push only after Report Studio is complete and production-ready.

## Milestone 4: Products

Goal: Make Product Studio the operational control center for product readiness, launch, public display, retirement, and dead-stock recovery.

Features:

- Product Retirement Workflow
- Dead Stock Rescue
- Product Story Cards
- Product Readiness Score
- Product Photo Shot List
- Product Launch Checklist

### Phase 4.1: Product Readiness Scoring Foundation

Implement:

- Service that calculates readiness score from product fields, photos, license status, cost snapshot, inventory, POS/public visibility, description, model analysis, price, and recent sales.
- Store score snapshots only if history is useful; otherwise calculate live and document the decision.
- Add score breakdown to Product Studio and API.
- Add readiness filters to product admin lists.

Production checks:

- Tests cover score calculation with complete/incomplete products.
- License risks reduce score strongly.

Commit after this phase.

### Phase 4.2: Product Launch Checklist

Implement:

- Checklist model/template or structured product launch status fields.
- Required launch items: license verified, model analyzed, cost snapshot, product photos, POS tile, public description, inventory target, market test plan, safety/care notes.
- Product Studio checklist UI with completion, reopen, notes, and audit events.
- Launch gate warning before making a product public/POS visible if critical items are incomplete.

Production checks:

- Tests cover launch gate behavior.
- Admin override requires explicit reason and audit log.

Commit after this phase.

### Phase 4.3: Product Photo Shot List

Implement:

- Photo shot checklist per product.
- Default shot types: hero, scale-in-hand, color variants, close-up, packaging, booth display, POS tile.
- Connect shot completion to readiness score.
- Show missing photo needs in Product Studio.

Production checks:

- Tests cover checklist persistence and readiness integration.
- UI handles products with no images.

Commit after this phase.

### Phase 4.4: Product Story Cards

Implement:

- Admin-managed story card content: what it is, who it is for, materials, care, customization options, safety notes, and internal compliance notes.
- Public product detail modal or “more details” panel.
- Optional QR/sign reuse for Promotion milestone.
- Audit content changes.

Production checks:

- Tests cover public rendering and admin validation.
- Do not expose internal compliance notes publicly.

Commit after this phase.

### Phase 4.5: Dead Stock Rescue

Implement:

- Service that identifies stagnant inventory using inventory age, quantity on hand, last sold date, sales velocity, product margin, seasonality, trend score, and market fit.
- Suggested actions: discount, bundle, market-only, hide online, retire, re-photo, change color, or stop reprinting.
- Admin workflow to accept/dismiss/action recommendations.
- Tie accepted recommendations to product, inventory, promotion, or market prep actions.

Production checks:

- Tests cover dead-stock scoring and accepted actions.
- Recommendations are explainable.

Commit after this phase.

### Phase 4.6: Product Retirement Workflow

Implement:

- Guided retirement flow: discount remaining stock, hide public page, remove POS visibility, preserve historical analytics, mark license/model status, block accidental reprint, archive product when safe.
- Guardrails that prevent deleting historical sales/order context.
- Clear admin UI and API endpoint.
- Audit every transition.

Production checks:

- Tests cover retirement, blocked reprint/public/POS behavior, and historical analytics preservation.

Commit after this phase.

### Milestone 4 Completion Gate

- Run product, public storefront, POS visibility, inventory, trend-scout integration, API, and migration tests.
- Verify Product Studio UI on desktop and mobile widths.
- Update docs and scorecard.
- Push only after all Products phases are production-ready.

## Milestone 5: Printers

Goal: Capture failure causes and turn printer reliability into production intelligence.

Feature:

- Printer Maintenance Autopsy

### Phase 5.1: Failure Autopsy Data Model

Implement:

- Print failure autopsy model linked to print job, printer, product, filament spool, user, and optional model asset.
- Failure categories: spaghetti, adhesion, clog, layer shift, support failure, filament issue, power/user interruption, slicer/settings, unknown.
- Fields for severity, notes, photo/reference file, corrective action, maintenance required, and resolved status.
- Migration and schema.

Production checks:

- Tests cover model and relationships.

Commit after this phase.

### Phase 5.2: Failure Autopsy Workflow

Implement:

- When a print job is marked failed, prompt for the 3-5 question autopsy.
- Allow quick entry from print job detail.
- Add reopen/edit/resolve workflow.
- Audit events for failure autopsy created/updated/resolved.

Production checks:

- Tests cover failed print transition requiring or suggesting autopsy.
- UI handles quick mobile entry.

Commit after this phase.

### Phase 5.3: Printer Reliability Reporting

Implement:

- Printer reliability cards showing failure count, failure rate, common causes, recent trend, affected products, and filament correlation.
- Feed cost engine failure-rate adjustments where appropriate.
- Add API endpoint and Report Studio integration if Report Studio exists.

Production checks:

- Tests cover reliability summary calculations.
- Handles sparse data gracefully.

Commit after this phase.

### Milestone 5 Completion Gate

- Run printer, print job, cost engine, analytics, API, and migration tests.
- Update docs and scorecard.
- Push only after Printers milestone is complete.

## Milestone 6: Orders / Custom Orders

Goal: Make pickup logistics reliable across web orders, custom orders, POS deposits, and markets.

Feature:

- Local Pickup Scheduler

### Phase 6.1: Pickup Slot Foundation

Implement:

- Pickup slot/location model for market pickup, porch/local pickup window, arranged handoff, or other configured pickup locations.
- Link pickup schedules to orders and custom requests.
- Add settings for pickup availability and instructions.
- Migration, forms, schemas, and API endpoints.

Production checks:

- Tests cover slot creation, validation, and permissions.

Commit after this phase.

### Phase 6.2: Customer Pickup Selection

Implement:

- Public checkout pickup selector.
- Custom order pickup selector after quote/deposit where appropriate.
- Confirmation page and email-ready content if email sending exists.
- Validation for unavailable/full/past slots.

Production checks:

- Tests cover checkout and custom request pickup selection.
- Public UI is mobile-friendly and clear.

Commit after this phase.

### Phase 6.3: Internal Pickup Board

Implement:

- Admin/staff board grouped by pickup date/location/market.
- Show payment status, order status, customer contact, items, notes, and “ready/handed off/no-show” actions.
- Generate prep tasks for pickup batches.
- Audit status changes.

Production checks:

- Tests cover ready/handed-off/no-show transitions and permission rules.

Commit after this phase.

### Milestone 6 Completion Gate

- Run orders, custom orders, public checkout, prep task, API, and migration tests.
- Update docs and scorecard.
- Push only after Orders / Custom Orders milestone is production-ready.

## Milestone 7: Booth Mode

Goal: Create a market-day command screen separate from POS that helps the owner run the booth in real time.

Feature:

- Booth Break-Even Timer

### Phase 7.1: Booth Mode Foundation

Implement:

- Booth Mode route under the market/POS domain, depending on the cleanest existing architecture.
- Staff-accessible screen optimized for tablet/phone.
- Select active market and POS session.
- Show current revenue, total costs, booth/application/travel expenses where available, expected cash, payment mix, and units sold.
- Feature flag and permission enforcement.

Production checks:

- Tests cover auth, feature flag, market/session selection, and empty state.

Commit after this phase.

### Phase 7.2: Break-Even Timer

Implement:

- Break-even service that calculates remaining dollars to cover booth/application/linked expenses.
- Once break-even is reached, switch display to profit tracking.
- Show elapsed market time and sales pace.
- Warn when current pace is unlikely to break even before close.

Production checks:

- Tests cover calculations, no-cost markets, partial expense data, and completed markets.

Commit after this phase.

### Phase 7.3: Booth Mode Action Hints

Implement:

- Real-time hints from sales/inventory: push slow-but-high-margin item, refill impulse tray, check low market-bin stock, follow up on custom leads.
- Do not interrupt checkout.
- Add manual dismiss/snooze.
- Audit important accepted actions.

Production checks:

- Tests cover hint generation and dismissal.
- UI remains fast and touch-friendly.

Commit after this phase.

### Milestone 7 Completion Gate

- Run POS, market, analytics, inventory, API, and UI-focused tests.
- Verify mobile/tablet layout.
- Update docs and scorecard.
- Push only after Booth Mode is complete.

## Final Program Completion Gate

After all milestones are complete:

1. Run full migration upgrade against a clean MariaDB database.
2. Run the full test suite:

```bash
uv run pytest
```

3. Run lint/format checks used by the repo.
4. Run API/OpenAPI tests.
5. Run targeted browser checks for public pages, admin pages, Product Studio, Report Studio, market command center, POS, Booth Mode, and pickup scheduler.
6. Confirm all new modules work with feature flags enabled and disabled.
7. Confirm audit events dispatch for critical workflows.
8. Confirm no secrets are staged.
9. Confirm no generated duplicate files or accidental `* 2.py`, `* 2.html`, `* 2.md` files were introduced.
10. Update:
    - `TODO.md`
    - `docs/production_readiness_scorecard.md`
    - `README.md` or relevant module docs
    - API docs if endpoints changed
11. Push the final branch state.

Only call the entire program complete when every milestone has been pushed and all final production-readiness gates pass.

## Reporting Format After Each Phase

After each phase, report:

- Phase completed
- Files changed
- Migrations added
- Tests/checks run and results
- Commit hash
- Remaining risks or blockers
- Next phase

## Reporting Format After Each Milestone

After each milestone, report:

- Milestone completed
- Phase commit hashes
- Tests/checks run and results
- Push result and remote branch
- Production-readiness status
- Any remaining risks before starting the next milestone

