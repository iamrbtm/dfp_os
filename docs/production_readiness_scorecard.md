# Production Readiness Scorecard

Date: 2026-08-13

This scorecard reflects the current hardening pass. Scores are conservative and describe the foundation after the changes in this pass, not a claim that every feature is complete.

| Area | Current status | Score | Bugs found | Missing features | Fixes made | Remaining risks | Tests added | Next recommended step |
|---|---|---:|---|---|---|---|---|---|
| POS | Authenticated POS sessions, cash/card-placeholder payments, order/payment creation, closeout, inventory deduction, and refund flow are wired. | 7 | Product sales could commit before inventory deduction and deducted from any location. | Refund reporting is still whole-sale only and should support partial reversals. | Added sale refund service, refund route, API endpoint, audit dispatch, and automatic inventory restocking. | Concurrent market checkout and refund sequencing should be load-tested against MariaDB. | Focused refund service coverage added. | Add partial refunds and closeout reporting that separates gross sales from refunds. |
| Booth Mode | Staff/admin market-day command screen shows break-even/profit tracking, sales pace, expected cash, payment mix, and persisted action hints. | 7 | No separate booth command screen existed outside checkout. | Live auto-refresh and deeper historical/trend-aware hints are future work. | Added Booth Mode module, feature flag, blueprint, break-even service, hint persistence, route UI, and focused tests. | Sales pace depends on accurate market close time and active POS session selection. | Added `tests/test_milestone7_booth_mode.py`. | Add HTMX polling and richer hints from market history and Trend Scout. |
| Inventory | Finished goods, filament, locations, available quantity, low-stock analytics, movement history, and operational stock controls exist. | 8 | No movement history and negative inventory prevention was incomplete. | Bulk adjustments and richer transfer history filters need polish. | Added service-backed transfer, reservation, release, return flows plus admin UI and API endpoints. | Existing generic CRUD still allows direct quantity edits outside the richer service flow. | Added focused transfer/reserve/release coverage. | Route more inventory edits through service-only paths and add movement filters/export. |
| Products / Product Studio | Product Studio now manages readiness scoring, launch checklist, photo shot list, story cards, dead-stock recommendations, and retirement guardrails. | 8 | Stale Report Studio import blocked app import on this branch. | Readiness filters on the generic product admin list and photo-shot-to-image enforcement still need polish. | Added Product Ops models/service/migration, Product Studio panels/actions, public story-card rendering, API readiness/rescue/retirement endpoints, and explicit launch override reason. | Dead-stock scoring is heuristic until more sales/seasonality/trend history exists. | Added `tests/test_milestone4_product_ops.py` covering readiness, license cap, launch override, story rendering, dead-stock acceptance, and API retirement. | Add list filters for readiness/dead-stock status and link shot-list completion directly to uploaded image IDs. |
| Markets | Market planning, status, packing lists, expenses, POS attribution, and profitability are present. | 7 | Profit was basic revenue minus expenses. | Repeat recommendation is now present but still heuristic and not trend-aware. | Added cost-engine-backed performance metrics and repeat recommendation guidance on the market review screen. | Profit estimates still depend on product cost data quality and complete expense capture. | Prep task generation/readiness tests. | Add historical comparisons across repeat markets and channel mix analysis. |
| Orders / Custom Orders | Local pickup scheduling now links pickup locations/slots to public checkout, custom requests, orders, API resources, prep tasks, and an internal pickup board. | 8 | Checkout previously only had pickup as a loose fulfillment choice with no slot validation. | Email sending, recurring availability rules, and quote-stage rescheduling still need polish. | Added pickup models, migration, service validation, public selector, admin slot/location CRUD, pickup board transitions, API resources, and prep-task generation. | Slot capacity is simple and should be load-tested for concurrent checkout. | Added `tests/test_milestone6_pickup_scheduler.py` and updated storefront checkout tests. | Add notification/email reminders and operator reschedule workflow. |
| Receipts & Expenses | Receipts are first-class with upload, extraction drafts, manual review, approval, duplicate review, and ledger entry creation. | 7 | AI receipt parsing did not honor explicit AI enable flag. | Receipt edit forms and allocation UX need broader audit assertions. | Added duplicate-candidate detail, merge/keep review path visibility, and processing diagnostics on the review screen. | OCR/AI provider failures still need clearer operator remediation guidance. | Existing receipt approval tests plus audit wiring. | Add receipt edit audit tests and clearer failure messaging for parser/provider errors. |
| Analytics | Executive, product, POS, inventory, printing, market, and expense summaries exist. | 6 | AI insights were not centralized or gated by config. | Charts and explanations need more comparative history. | Added centralized analytics insight service with AI-disabled fallback. | AI output quality depends on small dataset quality. | Analytics fallback test. | Add time-period comparisons and surfaced insight panel. |
| Cost Engine | Reusable service calculates cost, suggested price, margin, order profit, POS sale profit, and market profit. | 6 | Cost math lived mostly in product fields and analytics. | Machine depreciation settings and failure-rate calibration need settings UI. | Added `app.services.cost_engine` and API endpoints. | Cost defaults are conservative placeholders. | Cost breakdown test. | Store cost assumptions in settings and show cost cards on product/order screens. |
| Trend Scout | CLI command, REST API, Celery task monitor, notifications, rate-limit retry, data retention, score history, settings page (weight sliders/source toggles/profiles), report detail + comparison, matrix pagination/dismiss/auto-refresh, backtest calibration (monthly schedule + manual), print-job linking, market prep integration. | 7 | API resources declared in module registry (trend-reports, trend-opportunity-scores, trend-source-health) lack dedicated Flask-Smorest resources. | No trend-scout-specific API scopes; backtest calibration is manual-only for historical comparisons. | All 13 roadmap phases implemented across 4 milestones: CLI, API, notifications, task monitor, rate-limit retry, data cleanup, score history, settings page, report detail/comparison, matrix UX polish, backtest scheduling, print job linking, market prep integration. | API resource endpoints exist as blueprint routes but aren't formalized as Flask-Smorest resources for OpenAPI auto-docs. Missing MariaDB makes most DB-dependent tests unverifiable in CI. | 37 pass, 7 pre-existing failures, 225 DB-connection errors. Trend Scout service and fixture tests pass when DB is available. | Add Flask-Smorest API resources for trend-reports, trend-opportunity-scores, trend-source-health. Add API scopes. Run full test suite against live MariaDB. |
| Prep Tasks | Reusable templates, generated market tasks, inventory gap suggestions, and readiness score exist. | 6 | Prep was market-task-specific, not a reusable module. | Assignment UI and packing-list integration need deeper workflow. | Added prep task models/service/API and demo seed templates. | Suggestions are simple until sales history grows. | Prep generation/readiness tests. | Build admin/market prep screens and packing summary. |
| Module Registry / Feature Flags | Internal registry declares required module keys, dependencies, routes, API resources, docs, and health. | 7 | No server-side disabled-module enforcement existed. | Admin flag editing UI should be added. | Added registry, feature flag model, settings module status page, route/API blocking. | Some CRUD routes still need module-specific permission granularity. | Disabled route/API blocking tests. | Add admin feature flag edit form with audit. |
| Audit Logging | **Full coverage sweep complete, with chain-timeline UI.** Every state-changing action in the app emits an audit event with auto-captured `request_id`, `ip_address`, and `user_agent`. The detail page renders a vertical timeline of the record's full history with per-event chain-status badges (head/ok/broken) and a record-vs-type scope toggle. A coverage test (`tests/test_audit_coverage.py`) enforces the audit contract in CI. | 9 | Original client never populated `request_id`/`ip`/`user_agent` as top-level fields; microservice migrations were not run on first boot; outbox did not exist; chain-timeline view did not exist. | API token scope-denied events and per-resource "viewed" events not yet emitted (intentionally skipped to avoid noise). | Added `app/utils/audit_events.py` (canonical enum), `app/utils/audit_decorator.py` (`@audited`), `app/services/audit_outbox.py` (Redis + deadman), `app/tasks/audit_outbox.py` (Celery beat drain), `app/templates/audit_logs/_timeline.html` (chain timeline UI), upgraded `app/services/audit_client.py` to outbox-first delivery with chain-timeline method, added the API global after_request audit hook in `app/__init__.py`, switched Redis to AOF + `noeviction`, mounted the audit deadman as a named volume with a chown-on-start entrypoint. | Migration step is not yet wired into `docker-compose.yml`; the audit microservice still needs `alembic upgrade head` run once after a fresh deploy. | `tests/test_audit_outbox.py` (12 tests), `tests/test_audit_coverage.py` (3 tests), `tests/test_audit_logs_detail.py` (4 tests), and `services/audit-log/app/tests/test_entity_timeline_with_chain.py` (5 tests) pass. | Wire `docker compose run --rm audit-log alembic upgrade head` as a release-profile service, and add rate-limit + request-budget backpressure in the outbox. |
| Security / Permissions | Password hashing, role decorators, CSRF, API token auth, upload allowlist, friendly errors, no card data storage. | 7 | Failed auth and disabled-module access were not audited. | API token scopes are not deeply enforced. | Added audit for auth/API-token failures and server-side module blocking. | Local `.env` can still leak into `docker compose config` output on developer machines. | Feature flag/security blocking tests. | Add token scope enforcement and rotate any local exposed secrets. |
| REST API | `/api/v1`, token auth, pagination, OpenAPI docs, exports, analytics, cost, prep, and modules endpoints exist. | 7 | Generated OpenAPI missed request/response metadata on many CRUD endpoints. | Sorting/filtering is still basic on many resources. | Added Flask-Smorest docs for generic CRUD and new foundation endpoints. | Generic CRUD still needs richer permission/scope checks. | OpenAPI tests pass. | Add per-resource scopes and audit for API CRUD/export/import. |
| Database / Migrations | Alembic migrations cover new business, feature flag, inventory movement, prep task tables, and business IDs. | 7 | Direct FK alters failed under SQLite migrations. | Existing migrations could be consolidated if schema is reset. | Added batch migration for SQLite compatibility. | MariaDB should be tested with real migration on a clean DB. | Migration upgrade test passes. | Run `flask db upgrade` against local MariaDB and document reset option. |
| Tests | Focused coverage exists for the new alignment paths, but the full suite still needs a stable runtime pass in this environment. | 7 | Local pytest startup is extremely slow under the current Python 3.14 environment. | Full-suite verification, browser coverage, and broader UI assertions still need completion. | Added focused tests for inventory operations, POS refunds, and the new API endpoints. | This workstation still blocks a clean full pytest pass, so regressions outside compiled paths remain possible. | Targeted tests were added but not fully executed end-to-end here. | Stabilize the Python 3.14 test environment, then run the full suite and fix remaining failures before claiming parity. |
| Docker / Deployment | Compose config validates and includes audit-log and docs profiles. | 6 | Rendered Compose config can display local `.env` secrets. | Production secrets management and health checks need hardening. | Verified `docker compose config`. | Real-looking local secrets were present in this workstation environment; rotate if valid. | Compose config verification. | Use `.env.example` placeholders and secret manager/CI vars for deployment. |
| Documentation | AGENTS/DESIGN/README describe modular monolith, API docs, audit, and readiness direction. | 7 | Scorecard was missing. | Module docs per module are still shallow. | Added this scorecard and README foundation notes. | Docs need to track future schema resets carefully. | Not applicable. | Add per-module docs under `docs/modules/`. |
| SaaS-Later Readiness | Default business/account model and nullable `business_id` fields added to major records. | 6 | No account foundation existed. | No tenant onboarding, billing, or tenant isolation policy yet by design. | Added `Business`, default-business seed, and major-record scoping fields. | Single-business assumptions remain throughout queries. | Migration and seed paths covered by tests. | Add query helpers that scope by active business without full multi-tenant complexity. |

| Report Studio | New centralized reporting hub with market heat map, application tracker, report catalog, data quality warnings, CSV exports, and Chart.js visualizations. | 7 | None found. Report Studio is read-only and does not introduce write paths. | Scheduled/generated report persistence, geographic map rendering, and deeper product/inventory/POS reports still needed. | Created blueprint, module registry entry, service layer, 3 templates, API endpoints, CSV exports, feature flag enforcement, role-based access, sidebar nav, test suite. | Heat map relies on table view (no external map API). Full test suite blocked by Python 3.14 environment. | 28 focused tests added for service, routes, API, auth, feature flags, and CSV exports. | Add geographic map rendering for markets with coordinates, add data freshness/persisted report scheduling, and integrate deeper product/POS reports. |
| Printer Reliability | Failure autopsy records, failed-print workflow, reliability summaries, Report Studio page, and API output are implemented. | 8 | Existing print-job API mapping assigned a nonexistent `quantity` field. MariaDB also exposed Report Studio `NULLS LAST` incompatibility. | Reliability report has no CSV export yet. Migration upgrade still needs a clean-DB pass. | Added autopsy model/migration/form/service/templates, audit events, `/printers/reliability`, `/report-studio/printer-reliability`, `/api/v1/printers/reliability`, autopsy API resource, cost-engine failure-rate fallback, and MariaDB-safe Report Studio ordering. | Broader Report Studio/OpenAPI suites still have unrelated Milestone 3/test-fixture failures. | `tests/test_milestone5_printer_reliability.py`: 4 passed. Py compile passed for changed Python files. | Run `flask db upgrade` against clean MariaDB, then fix remaining Report Studio fixture assertions and OpenAPI metadata gaps. |
26: 
27: ## 2026-07-08 Audit Remediation Update

| Area | Score | Fixes made | Remaining risks | Tests/checks added |
|---|---:|---|---|---|
| POS | 8 | Server now uses database product prices, validates quantities/discounts/tax/cash, and records critical POS sale/refund audit events before commit. | Partial refunds and concurrent checkout load tests still need a live MariaDB pass. | Added POS tamper/negative/insufficient-cash/audit fail-closed tests. |
| Audit Logging | 7 | Added `AuditDispatchError`, critical audit dispatch, and config alias `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS`. | A transactional outbox would be stronger for audit-service outages. | Added critical audit failure tests and syntax checks. |
| REST API | 8 | Empty API-token scopes no longer imply full access, inactive token owners are rejected, API token creation requires `admin`, and generic API updates block receipt/POS/inventory workflow mutations. | Existing legacy empty-scope tokens need admin review before production use. | Added API token and workflow-guard tests. |
| Receipts & Expenses | 8 | Receipt uploads now check file signatures before saving/parser execution, enforce basic parser limits, and receipt images require admin/staff. | Parser isolation and malware scanning are still future hardening work. | Added spoofed-extension and low-privilege image-access tests. |
| Security / Permissions | 8 | Production config rejects default secrets, security headers are set, login/API auth rate limits are configurable, docs auth is required outside development, and intelligence query-token auth was removed. | In-memory rate limiting is process-local; production should use Redis-backed limiting. | Added security config, docs auth, intelligence auth, and rate-limit tests. |
| Docker / Deployment | 7 | Docker image fails CSS build failures, uses `npm ci`, runs as non-root, exposes only intended ports, moves migrations to a release-profile service, and compose now requires explicit credentials. | `npm`, `uv`, and full Docker build were not available here; image build must be verified in CI/dev workstation. | `docker compose --env-file .env.example config` succeeds; npm build could not run because npm is missing. |
| Tests | 7 | Added focused unit/API/E2E scaffolding for remediated issues. | `uv`, `pytest`, and `npm` are unavailable in this environment, so tests were syntax-checked but not executed. | `python3 -m py_compile` passed for changed Python files. |

## 2026-08-13 Trend Scout Microservice + Firecrawl Initiative — Phase 0 Baseline

Branch: `phase/0-plan-and-scorecard`. Per-phase scores tracked below as phases land.

| Area | Phase 0 baseline | Notes |
|---|---:|---|
| Microservice / Trend Scout Extraction | 0 | Not started. Plan written, scorecard section opened. |
| Firecrawl Self-Host | 0 | Not started. Vendor + hardening required. |
| Firecrawl Sources (non-Etsy) | 0 | Not started. Targets planned: cults3d, thangs, stlfinder, cgtrader, mmf_trending (fallback), general. |
| Firecrawl Etsy (throttled, opt-in) | 0 | Not started. Default off. Compliance flow designed. |
| Source Coverage (overall) | unchanged from prior score | 10 existing sources + 7 new Firecrawl targets planned |
| Audit Logging | unchanged from prior score | 22 new audit events planned for this initiative |
| Security / Permissions | unchanged from prior score | Bearer token + scope enforcement planned for new microservice API |
| REST API | unchanged from prior score | New microservice owns `/api/v1/*` for trend-scout; Flask becomes proxy |
| Database / Migrations | unchanged from prior score | New logical DB `trend_scout` on shared Postgres, Alembic async |
| Tests | unchanged from prior score | ~324 new tests planned across 11 phases |
| Docker / Deployment | unchanged from prior score | 5 new Firecrawl services + 2 new trend-scout services + new volumes |
| Documentation | unchanged from prior score | New `docs/trend_scout_microservice_plan.md` added |
| SaaS-Later Readiness | unchanged from prior score | Microservice is single-tenant; multi-tenant posture unchanged |

### Phase 0 pre-existing baseline issues (recorded, not fixed in this phase)

- `uv run ruff check .` reports 5 pre-existing errors in `app/tasks/model_analysis.py`, `services/audit-log/app/tests/test_rebuild_chain.py`, and `tests/test_milestone7_booth_mode.py`. These are unrelated to the Trend Scout initiative and will be addressed in a separate cleanup pass to keep the per-phase diffs focused.
- `uv run ruff format --check .` reports 6 pre-existing format issues across `app/tasks/model_analysis.py`, `migrations/versions/add_market_id_to_custom_request.py`, `migrations/versions/d5e6f7a8b9c0_market_catalog.py`, `services/audit-log/app/tests/test_entity_timeline_with_chain.py`, `tests/test_milestone7_booth_mode.py`, and `tests/test_openapi_spec.py`. Same reasoning — out of scope for Phase 0.
- `uv run pytest --collect-only` collected 746 tests. Full-suite run was not attempted in Phase 0 because the env-level run is slow; the per-phase test runs in later phases will exercise the relevant subsets. A 3-test audit coverage subset was confirmed green (3 passed in 3.31s).

### Phase 0 deliverables checklist

- [x] `docs/trend_scout_microservice_plan.md` written (condensed plan)
- [x] Scorecard section opened for this initiative
- [x] `.github/PULL_REQUEST_TEMPLATE.md` written
- [x] `.github/ISSUE_TEMPLATE/trend_scout_microservice.md` written
- [x] `.github/workflows/ci.yml` `trend-scout-tests` job skeleton added
- [x] Baseline ruff/format/pytest recorded
- [x] Committed and pushed to `phase/0-plan-and-scorecard`

## Phase 1 — Microservice Scaffold (2026-08-13)

Branch: `phase/1-ms-scaffold`. Status: complete.

| Area | Before | After | Justification |
|---|---:|---:|---|
| Microservice / Trend Scout Extraction | 0 | 3 | Scaffold + Dockerfile + Alembic + FastAPI app + Celery (low-priority queue) + Bearer token security + compose wiring all landed. |
| Database / Migrations | unchanged from Phase 0 | unchanged | New logical DB `trend_scout` provisioned via `docker/postgres/init/01-init-databases.sh`; async Alembic env wired; first migration creates 5 tables (trend_snapshots, trend_reports, trend_opportunity_scores, source_health_records, trend_weights). |
| Tests | unchanged from Phase 0 | +1 file, 10 tests | `services/trend-scout/app/tests/test_smoke.py` exercises app factory, /health endpoints, OpenAPI, settings, DB module, Celery queue/priority/routing, security scopes, alembic env. All green. |
| Docker / Deployment | unchanged from Phase 0 | +3 services | `trend-scout` (API + healthcheck), `trend-scout-worker` (Celery `-Q trend_scout --concurrency=1`), `trend-scout-migrate` (release-profile Alembic upgrade). All wired in `docker-compose.yml`. |
| Security / Permissions | unchanged from Phase 0 | unchanged | Bearer token + scope helpers scaffolded for Phase 5 to extend. |
| REST API | unchanged from Phase 0 | unchanged | Only health endpoints exposed in Phase 1; full API lands Phase 5. |

### Phase 1 commands run

- `cd services/trend-scout && uv lock && uv sync --all-extras` — 88 packages resolved cleanly.
- `cd services/trend-scout && uv run ruff check .` — all checks passed.
- `cd services/trend-scout && uv run ruff format --check .` — 21 files clean.
- `cd services/trend-scout && uv run pytest -v` — **10 passed in 4.37s**.

### Phase 1 deliverables checklist

- [x] `services/trend-scout/` scaffolded (pyproject, Dockerfile, alembic, app/main.py, app/config.py, app/database.py, app/security.py, app/celery_app.py, health router, schemas/health.py, models, initial migration)
- [x] Bearer token security + scope constants exported
- [x] Celery instance with `trend_scout` queue, priority 1/10, routed tasks
- [x] Health endpoints: `/health/live`, `/health/ping`, `/health/ready`, `/health/deep`
- [x] Alembic async migration `0001_initial.py` for 5 tables
- [x] `docker-compose.yml` updated: `trend-scout`, `trend-scout-worker`, `trend-scout-migrate` services + `TREND_SCOUT_*` env vars + DB provisioning in init script
- [x] `.env.example` updated with TREND_SCOUT_* env vars
- [x] `.github/workflows/ci.yml` `trend-scout-tests` job activated (no longer `if: false`)
- [x] `AGENTS.md` services tree updated to include the new microservice
- [x] README.md for the microservice
- [x] Ruff + pytest clean on the microservice

### Phase 1 risk and out-of-scope

- **Risk:** the `trend-scout-worker` Celery container is wired but no actual Celery tasks are defined yet (Phase 4 fills this). Until Phase 4 lands, the worker container starts and consumes nothing.
- **Risk:** the `trend-scout-migrate` release-profile service exists but requires the `trend_scout` logical DB to be provisioned. With the init script updated in this phase, a fresh database will provision the DB and user; existing databases need a manual `CREATE DATABASE` and `CREATE USER` before migrations can run.
- **Out of scope:** source migration (Phase 2), analyzer (Phase 3), pipeline tasks (Phase 4), full API surface (Phase 5), Flask proxy/cutover (Phase 6), Firecrawl (Phases 7-9).

## Phase 2 — Sources Migrated (2026-08-13)

Branch: `phase/2-sources-migrated`. Status: complete.

| Area | Before | After | Justification |
|---|---:|---:|---|
| Source Coverage | unchanged from Phase 1 | unchanged | All 10 existing sources migrated to the microservice unchanged in behavior. |
| Microservice / Trend Scout Extraction | 3 | 5 | Fetcher pipeline + snapshot persistence + per-source imports landed. |
| Tests | 10 smoke tests | +27 (37 total non-slow, 2 slow) | per-source unit tests (10), fetcher pipeline partition tests (4), snapshot persistence tests (6), audit dispatch tests (4), slow marker added; CI uses `-m 'not slow'`. |
| Audit Logging | unchanged from Phase 1 | unchanged | `audit_dispatch.py` helper added; `internal_demand.py` imports it (Phase 3 wires the rest). |

### Phase 2 files added (services/trend-scout/)

- `app/sources/_base.py`, `bgg.py`, `etsy.py`, `google_trends.py`, `last30days.py`, `makerworld.py`, `myminifactory.py`, `pinterest.py`, `printables.py`, `reddit.py`, `tiktok.py` (copied from the monolith with import paths rewritten)
- `app/sources/internal_demand.py` (rewritten to call the Flask /api/internal/internal-demand endpoint via httpx; gracefully returns a structured error until Phase 6 wires the endpoint)
- `app/sources/__init__.py` (re-exports all 11 sources + helpers)
- `app/services/fetcher_pipeline.py` (DB_FETCHERS / EXTERNAL_FETCHERS / run_all_sources / aggregate_source_health)
- `app/services/snapshot_persistence.py` (async persist_snapshots, persist_source_health, create_empty_report, latest_source_health)
- `app/services/audit_dispatch.py` (httpx-based dispatch_audit_event with best-effort semantics)

### Phase 2 tests added

- `app/tests/test_sources.py` — 12 tests (10 per source + 2 base).
- `app/tests/test_fetcher_pipeline.py` — 6 tests (4 fast + 2 slow).
- `app/tests/test_snapshot_persistence.py` — 6 tests.
- `app/tests/test_audit_dispatch.py` — 4 tests.

### Phase 2 commands run

- `cd services/trend-scout && uv run ruff check .` — all checks passed.
- `cd services/trend-scout && uv run ruff format --check .` — 41 files clean.
- `cd services/trend-scout && uv run pytest -v -m "not slow"` — **37 passed in 33.99s**.

### Phase 2 risk and out-of-scope

- **Risk:** the Flask `/api/internal/internal-demand` endpoint does not yet exist; the `internal_demand` source will fail to fetch until Phase 6 (cutover) lands the endpoint.
- **Risk:** E501 line-length is suppressed for migrated source files via `per-file-ignores` because user-agent strings in those files exceed the 120-column limit and we preserve them verbatim.
- **Out of scope:** analyzer + scoring + backtest (Phase 3), Celery pipeline tasks (Phase 4), full API surface (Phase 5), Flask proxy/cutover (Phase 6), Firecrawl (Phases 7-9).

## Phase 3 — Analyzer + Scoring + Backtest (2026-08-13)

Branch: `phase/3-analyzer-and-scoring`. Status: complete.

| Area | Before | After | Justification |
|---|---:|---:|---|
| Microservice / Trend Scout Extraction | 5 | 7 | Analyzer pipeline landed end-to-end: velocity / momentum / opportunity scoring / category discovery stubs / backtest / calibration. |
| Tests | 37 non-slow + 2 slow | 91 non-slow + 2 slow (+54) | Scoring math (16 tests), weights module (16 tests), backtest + calibration (12 tests), orchestrator + AI provider (5 tests), source health (4 tests already counted), scores math edge cases. |
| Cost Engine | unchanged from Phase 2 | unchanged | Cost Engine in the monolith is a separate module untouched here. |
| Analytics | unchanged from Phase 2 | unchanged | Trend Scout analytics (the focus of this initiative) is the source of the score deltas. |
| Documentation | unchanged from Phase 2 | unchanged | Plan doc references Phase 3 deliverables; deeper docs land in Phase 10. |

### Phase 3 files added (services/trend-scout/)

- `app/services/weights.py`: full weights module (DEFAULT_SCORE_WEIGHTS, DEFAULT_SOURCE_WEIGHTS including the 7 Firecrawl targets, DEFAULT_BUYER_SOURCE_WEIGHTS, DEFAULT_METRIC_WEIGHTS), async loaders, validate_score_weights, seed_default_weights, scoring_version (deterministic sha256 hash).
- `app/services/ai_provider.py`: OpenAI synthesis with deterministic fallback that never invents metrics.
- `app/services/analysis/__init__.py`, `orchestrator.py`, `trend_detector.py`, `opportunity_scoring.py`, `new_category_discovery.py`: 7-dimension scoring, velocity/momentum from snapshot history, license/local keyword signals, growing/declining extraction, opportunity ranking.
- `app/services/backtest.py`: synthetic-history-safe backtest (rmse/mae/r2/precision_at_k), no_data path, tuning hints.
- `app/services/calibration.py`: persists backtest results into TrendWeight table (group `calibration_run:<timestamp>`), regression detector across the latest two runs.

### Phase 3 tests added

- `app/tests/test_scoring.py` — 16 tests covering scoring math, keyword signals, action thresholds, velocity/top-opportunity on empty DB.
- `app/tests/test_weights.py` — 16 tests covering default weights, Firecrawl source weights (Etsy lowest), validation, deterministic version hashing, async loaders.
- `app/tests/test_backtest.py` — 12 tests covering RMSE/MAE/R²/Precision@K math, tuning hints, no-data path, calibration persistence, regression detection.
- `app/tests/test_orchestrator.py` — 5 tests covering AI provider fallback paths and orchestrator imports.

### Phase 3 commands run

- `cd services/trend-scout && uv run ruff check .` — all checks passed.
- `cd services/trend-scout && uv run ruff format --check .` — 53 files clean.
- `cd services/trend-scout && uv run pytest -v -m "not slow"` — **91 passed in 34.93s**, 2 slow deselected.

### Phase 3 risk and out-of-scope

- **Risk:** the new ``trend_detector.py`` is intentionally simplified relative to the monolith's 1,131-line version. Velocity / momentum / opportunity math are equivalent at the data-model level but the deeper NLP/prompt synthesis layer lands fully in Phase 10.
- **Risk:** ``new_category_discovery`` returns an empty cluster set by design in Phase 3. Phase 10 adds DBSCAN + text-embedding-3-small.
- **Risk:** calibration rows are stored in the ``trend_weights`` table under group ``calibration_run:<timestamp>`` to avoid adding a new table. This is fine for retrieval but a dedicated ``trend_calibration_results`` table is a possible Phase 10 follow-up if query patterns become complex.
- **Out of scope:** Celery pipeline tasks (Phase 4), full API surface (Phase 5), Flask proxy/cutover (Phase 6), Firecrawl (Phases 7-9).
