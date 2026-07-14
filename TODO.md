# TODO.md

This file is the live working list for AI agents and humans collaborating in this repo.

## How To Use This File

- Read this file after `PROMPTS.md` and before making a plan.
- Update it when work starts, when scope changes, and when work completes.
- Keep items concrete and implementation-oriented.
- Mark completed work instead of deleting it immediately so recent progress stays visible.
- Prefer short status tags: `todo`, `in-progress`, `blocked`, `done`.

## Current Focus

- `done` Milestone 2 Phase 2.1: Promotion Module Foundation — models, forms, schemas, blueprint, routes, service, templates, module registry, migration, tests.

- `done` Production audit remediation pass for `docs/audit.md`: POS financial integrity, audit fail-closed, API token/workflow hardening, receipt upload/access security, production config/service auth, rate limiting, Docker hardening, and Playwright E2E scaffold.
- `done` Reorganized agent guidance into `AGENTS.md`, `PROMPTS.md`, `ARCHITECTURE.md`, and this file.
- `done` Built the public website + ecommerce storefront pass: polished public pages, session cart, online checkout, and payment fallback flow.
- `done` Refactored product asset storage so uploaded model/image/generated files follow the per-product and per-variant folder layout used in production file management.
- `done` Rebuilt Product Studio into isolated primary and variant accordions so each section owns its own fields, assets, previews, and cost calculations.
- `in-progress` Replace placeholder product pricing with evidence-backed cost snapshots, spool-aware material costing, historical print-job failure rates, and multi-axis profitability metrics.
- `done` **Phase 1: AI Design Trend Scout — Database & Foundation** — Created `TrendSnapshot` and `TrendReport` models, generated migration, set up `app/services/ai/trend_scout/` directory structure.
- `done` **Phase 2: AI Design Trend Scout — Source Integrations (The Fetchers)** — Built base utility (`_base.py` with rate limiter, UA rotation, `ScoutResult`), API fetchers (MyMiniFactory, Etsy, BGG), scrapers (MakerWorld, Printables, Reddit). All return standardized `ScoutResult` dicts. Pipeline orchestration in `trend_scout/__init__.py`.
- `done` **Phase 3: AI Design Trend Scout — Pipeline & Celery Task** — Concurrent pipeline via `ThreadPoolExecutor`, Celery task (`app/tasks/trend_scout.py`) with 15-min timeout, DB persistence of `TrendSnapshot` rows with per-source error isolation. Beat schedule set for Monday 6:00 AM. Beat container added to docker-compose.
- `done` **Phase 4: AI Design Trend Scout — Analysis & NLP Discovery** — Trend detector computes week-over-week velocity/momentum/cross-source correlation. Category discovery extracts noun phrases, embeds via `text-embedding-3-small`, clusters with DBSCAN. GPT-4o-mini synthesizes into `TrendReport` with summary, opportunities, growing/declining categories.
- `done` **Phase 5: AI Design Trend Scout — Flask Blueprint & Dashboard** — Blueprint at `/admin/trend-scout` with dashboard page, `/api/latest` and `/api/reports` JSON endpoints. Module registered in registry with nav entry. Template renders latest report summary, top 10 opportunities, growing/declining categories, pipeline meta, and past reports table with empty state.
- `done` **AI Design Trend Scout hardening pass** — Refactored trend scoring to ignore error-only snapshots, normalize keywords, weight source/item signal, preserve source timestamps, add deterministic no-AI summaries/category fallback, fix BGG/Etsy/Pinterest source issues, and add focused unit tests.
- `done` **Trend Scout buyer-intent expansion** — Added internal demand events for storefront/POS/customer-request signals, made internal demand the highest-priority Trend Scout source, and added optional Google Trends/search-interest and TikTok Research API adapters with safe not-configured fallbacks.
- `done` **Trend Scout opportunity decision matrix** — Split opportunity scoring into purchase intent, trend velocity, price resilience, low saturation, local fit, production fit, and license risk; included current catalog products alongside potential products with action recommendations.
- `done` **Phase 7: Source Health Dashboard** — Added stale-data age column (shows time since last scrape), provider setup status indicator (configured vs unconfigured sources with env var checks), and data freshness score (0–100 color-coded) to the Source Health table.
- `done` **Phase 9: Saved Views** — Added "Save View" button that persists current pill view, search query, filters, and sort column/direction to localStorage; auto-restores on page load.
- `done` **Phase 11: Production Verification** — Created `docs/trend_scout_setup.md` with API key setup guide for all 10 sources, env var reference, migration verification steps, Celery worker/beat run instructions, pipeline architecture diagram, scoring weights reference, and development guide.
- `done` **DFPos Intelligence microservice phases 1-4** — Scaffolded `services/intelligence/` with FastAPI/PostgreSQL/Alembic/Docker, health checks, internal bearer auth, Square item CSV staging import with sensitive payment-field stripping, old MariaDB schema-inspection snapshots, and historical alias mapping review models/APIs.
- `done` **DFPos Intelligence microservice phases 5-6** — Added warehouse sales facts plus product/seasonal/channel summaries from sanitized Square rows, and a deterministic Market Advisor that stores evidence-backed product quantity, print quantity, revenue, and risk recommendations.
- `done` **DFPos Intelligence microservice phases 7-10** — Added RAG-ready knowledge documents/chunks with lexical retrieval, safe allowlisted Ask DFP answers, Flask admin integration, and decision-outcome feedback records for recommendation follow-up.

## Next Priorities

- `done` Milestone 3: Report Studio — Module foundation, report catalog home, vendor market heat map, and market application tracker report.

- `todo` Normalize and map kept tables from the legacy import staging layer into warehouse fact tables.
- `todo` Extend DFPos Intelligence with current DFPos snapshot sync and approved-action workflows that can create prep tasks or print jobs after human confirmation.
- `todo` Compare implemented modules against the required modules list in `AGENTS.md` and note gaps.
- `todo` Audit API coverage under `/api/v1/` against the required resource list.
- `todo` Audit admin CRUD coverage for modules that now exist in models/services but may still need full UI flows.
- `todo` Review test coverage against the minimum expectations in `AGENTS.md`.

## Parking Lot

- `todo` Decide later whether a separate `ROADMAP.md` is still useful for longer-term planning beyond the active working list.
- `todo` Add milestone-based phases here if the project shifts from feature work into release planning.

## Recently Completed

- `done` Built legacy MariaDB import pipeline for DFPos Intelligence: raw row staging (`legacy_import_row_stage`), per-table manifests (`legacy_table_manifests`), review decision tracking (`legacy_table_review_state`), Alembic migration 0004, full API for import-all/list/review/delete, 12 targeted tests, and Flask client methods.
- `done` Added public storefront checkout with session cart, customer checkout form, Square payment-link integration, and Venmo fallback confirmation flow.
- `done` Upgraded the public website with richer home/shop/product pages plus 3D printing basics, returns, and customer policies pages.
- `done` Added focused storefront tests covering cart, Venmo checkout, and Square redirect behavior.
- `done` Added a dedicated live task tracker for agents.
- `done` Established a place for architecture-specific guidance outside `AGENTS.md` and `DESIGN.md`.
- `done` Established a dedicated prompts/workflow file for session-level agent behavior.
