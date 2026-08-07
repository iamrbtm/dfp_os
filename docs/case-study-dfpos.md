# DFPos — Dude Fish OS

*An operating cockpit for a family-run 3D printing business.*

---

## Short Summary (for portfolio)

DFPos (Dude Fish OS) is a full-stack, modular-monolith Flask application that serves as the complete operating system for Dude Fish Printing, a family-run 3D printing business in Clarksville, Tennessee. Built on Python 3.14 with PostgreSQL, Docker, and a Tailwind/Jinja/HTMX frontend, DFPos unifies a customer-facing public storefront, a staff/admin dashboard, a mobile-first point-of-sale system, a full REST API with OpenAPI documentation, a cost/pricing engine, market-preparation workflows, receipt and expense management, embedded analytics, and an audit-log microservice — all tied together by a server-side feature-flag and module registry that can enable/disable entire subsystems with safe runtime enforcement. The system answers the operator's core question — "what should we make, sell, restock, stop selling, improve, or prepare next?" — through real-time inventory intelligence, cost-based profitability, sales velocity tracking, and automated prep-task generation for upcoming vendor markets.

---

## Case Study

### 1. Business Context

Dude Fish Printing is a family-run 3D printing business relocating to Clarksville, Tennessee. They sell finished prints online, through Facebook, at vendor markets, via custom orders, and through word of mouth. Their product lanes span articulated dragons, fidget toys, flexi animals, personalized gifts, Clarksville/Tennessee-themed items, military-family-safe gifts, and custom orders.

The business needed a single, integrated system to replace fragmented tooling (spreadsheets, separate POS apps, manual receipt tracking, disjointed inventory records) with a production-minded application that could:

- Power a warm, trustworthy public storefront
- Enable fast, reliable checkout at busy vendor markets
- Track real-time inventory across printers, filament, and finished goods
- Calculate true per-unit costs and margins
- Generate market-prep checklists and packing recommendations
- Capture and categorize every expense through receipt workflows
- Surface analytics and business insights
- Maintain a complete, tamper-evident audit trail of every business action

---

### 2. Technology Stack

| Layer | Technology |
|---|---|
| **Runtime** | Python 3.14 |
| **Dependency Management** | `uv` (lockfile, pinning, command execution) |
| **Web Framework** | Flask 3.x (Werkzeug, Jinja2) |
| **Database** | PostgreSQL 17 (migrated from MariaDB) |
| **ORM** | SQLAlchemy 2.x (Declarative) |
| **Migrations** | Flask-Migrate / Alembic |
| **Auth** | Flask-Login, Werkzeug password hashing, role-based decorators |
| **Forms** | Flask-WTF / WTForms (browser validation) |
| **API** | Flask-Smorest (OpenAPI 3.0.3, Swagger UI, Redoc) |
| **API Schemas** | Marshmallow |
| **Styling** | Tailwind CSS (Node toolchain for asset compilation only) |
| **Frontend** | Server-rendered Jinja2 templates, HTMX for inline updates, Alpine.js for small UI interactions, Chart.js for analytics |
| **Background Jobs** | Celery + Redis |
| **File Storage** | Local filesystem with optional S3-compatible backend (MinIO/SeaweedFS) |
| **Containerization** | Docker + Docker Compose (non-root Gunicorn in production) |
| **Linting/Formatting** | Ruff, Black |
| **Testing** | Pytest (unit, service, API, E2E via Playwright) |

**Supporting microservices:**

- **Audit-log service** (`services/audit-log/`) — FastAPI + PostgreSQL + SQLAlchemy async; hash-chained, idempotent audit events with Redis Streams support
- **Slicer service** (`services/slicer/`) — FastAPI + Bambu Studio 2.7.1.62 / PrusaSlicer; 3D model slicing and native artifact generation
- **Intelligence service** (`services/intelligence/`) — FastAPI + PostgreSQL; historical data warehouse and Market Advisor

---

### 3. System Architecture

```text
                    ┌─────────────────────────────────────┐
                    │            Main App (Flask)          │
                    │   ┌────────┐ ┌───────┐ ┌─────────┐  │
                    │   │Public  │ │Admin  │ │  POS    │  │
                    │   │Site    │ │Dash   │ │  (/pos)  │  │
                    │   └────────┘ └───────┘ └─────────┘  │
                    │   ┌────────────────────────────────┐ │
                    │   │    REST API (/api/v1)          │ │
                    │   │  Flask-Smorest + Marshmallow   │ │
                    │   └────────────────────────────────┘ │
                    │   ┌────────────────────────────────┐ │
                    │   │    Business Services            │ │
                    │   │  (cost, pos, inventory, receipts, │ │
                    │   │   analytics, prep_tasks, etc.)  │ │
                    │   └────────────────────────────────┘ │
                    └───────────────┬─────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
      ┌───────▼──────┐      ┌───────▼──────┐     ┌──────▼──────┐
      │ Audit-log    │      │ Slicer       │     │ Intelligence│
      │ microsvc     │      │ microsvc     │     │ microsvc    │
      │ (FastAPI)    │      │ (FastAPI)    │     │ (FastAPI)   │
      └───────┬──────┘      └──────────────┘     └─────────────┘
              │
      ┌───────▼──────┐
      │ PostgreSQL   │
      │ (audit db)   │
      └──────────────┘
```

**Data flow:**

1. **Browser request** → blueprint route → WTForms validation → service layer → SQLAlchemy model → Jinja template or HTMX partial
2. **API request** → `/api/v1/` → API token authentication → Marshmallow schema validation → service → JSON response
3. **POS flow** → authenticated staff opens session → product/category selection → server-validated cart → checkout creates order + payment + inventory deduction atomically
4. **Audit trail** → every meaningful action dispatches a structured event to the audit-log microservice via the `AuditClient`, which hash-chains events for tamper evidence

**Key architectural constraints:**

- Business logic lives exclusively in service modules, never in routes or templates
- Money is always `Decimal`/`Numeric(10, 2)` — never float
- Module enforcement (feature flags) is server-side, not UI-only
- Audit logs are the source of truth for compliance; the main app database is never the audit store
- AI features (receipt parsing, trend scouting, product stories) are opt-in, always gated behind feature flags, and outputs are treated as draft suggestions requiring human review

---

### 4. Core Modules

The application is built as a modular monolith governed by a central `module_registry.py`. Each of the 22+ modules declares its key, feature-flag key, dependencies, blueprint names, API resources, required roles, health check, and documentation location. All enforcement is server-side.

| Module | Purpose |
|---|---|
| **public_site** | Marketing pages, gallery, custom order intake, contact forms |
| **auth** | Login/logout, password hashing, session management, rate limiting |
| **dashboard** | Operator dashboard answering "what needs attention now?" |
| **products** | Product Studio: readiness scoring, launch checklists, photo shot lists, license/compliance tracking, AI trend analysis |
| **inventory** | Finished goods, filament/materials, locations, movement history, stock alerts |
| **printers** | Printer fleet (Bambu A1/X1C/P1P), AMS multicolor unit tracking, reliability analytics |
| **print_jobs** | Print queue, production status, failure autopsy tracking |
| **customers** | Customer records linked to orders, POS, and custom requests |
| **orders** | Orders, line items, payments, refunds, local pickup scheduling |
| **custom_orders** | Custom order requests, deposits, notes, conversion workflow |
| **pos** | Mobile-first point-of-sale, session management, inventory deduction, closeout |
| **booth_mode** | Market-day command screen: break-even tracking, sales pace, payment mix |
| **markets** | Vendor market planning, applications, packing lists, sales attribution, profitability |
| **receipts** | Receipt upload, OCR/AI extraction drafts, manual review, approval → ledger entries |
| **expense_ledger** | Structured ledger entries from approved receipts |
| **analytics** | Executive, product, market, inventory, printing, expense, and POS analytics |
| **cost_engine** | Reusable cost/price/margin/profitability calculations |
| **prep_tasks** | Reusable prep templates, generated market tasks, readiness scores, packing guidance |
| **table_layouts** | Product placement grid planning for market tables |
| **trend_scout** | Autonomous AI trend monitoring across Etsy, Pinterest, Reddit, TikTok, Google Trends |
| **report_studio** | Centralized reporting hub with visualizations and CSV exports |
| **promotion** | Social content queue and market display sign generation |
| **notifications** | In-app notification alerts for trends, system events, workflow milestones |
| **intelligence** | Historical warehouse, Market Advisor, Ask DFP (microservice) |
| **settings** | Application settings, themes, module status, business configuration |
| **audit_logs** | Audit-log dispatch and admin visibility |
| **feature_flags** | Database/config-backed module enablement controls |
| **api_tokens** | API token management with scoped permissions |

---

### 5. Key Workflows

#### POS Cash Sale Lifecycle
1. Staff opens a POS session (optionally tied to a specific market)
2. Product tiles render from live catalog with real-time inventory availability
3. Cart is managed client-side with full server validation on checkout
4. Payment methods: cash (with change-due calculation), Venmo/Cash App/Apple Pay placeholders, external card placeholder — **no card number, expiration, or CVV fields anywhere**
5. On completion: an `Order` + `Payment` record is created, inventory is deducted via `InventoryMovement` rows, a `PosSale` with line items is recorded, and audit events are dispatched for `pos_session.opened`, `pos_sale.completed`, `inventory.deducted`
6. On session close: expected cash is computed from completed sales, compared against actual cash collected, and discrepancies are flagged

#### Receipt → Expense Ledger Workflow
1. User uploads a receipt image/PDF (extension allowlist + file signature validation + max size enforcement)
2. If AI parsing is enabled, ChatGPT (or Ollama) extracts draft fields — these are labeled as suggestions with confidence scores
3. User reviews and edits extracted data in a split-pane comparison view (source image alongside fields)
4. User approves the receipt — at this point, structured `ExpenseLedger` entries are created with cost allocations to categories (filament, booth fees, packaging, etc.)
5. If rejected, the receipt is marked rejected and available for re-review
6. Duplicate detection warns on matching vendor/date/amount combinations
7. Audit events recorded for: `receipt.uploaded`, `receipt.ai_parsed`, `receipt.edited`, `receipt.approved`, `receipt.rejected`

#### Cost Engine
The cost engine is a reusable service that computes true per-unit costs across all revenue channels:

- **Material cost** (filament grams × cost-per-gram from spool records)
- **Labor cost** (estimated print minutes × configurable labor rate)
- **Machine/depreciation cost** (print time × hourly machine rate)
- **Packaging cost** (configurable flat rate)
- **Payment fees** (configurable percentage for card transactions)
- **Failure-rate adjustment** (printer-specific failure rate from historical data)
- **Market/booth allocation** (when applicable)
- **Output**: material cost, labor cost, machine cost, total cost, suggested price, margin dollars, margin percent, profit per unit, profit per print hour, profit per market bin

#### Market Preparation
1. System generates prep tasks from reusable templates (count inventory, print restocks, pack supplies, prepare cash box, etc.)
2. Suggestions are computed from previous market sales, inventory levels, reorder targets, and print job queue
3. A "readiness score" aggregates completed tasks with visible inputs
4. Packing lists are assembled with suggested quantities per product
5. Booth Mode provides live market-day metrics: break-even line, gross margin, sales pace, payment mix, expected cash

---

### 6. Quality Attributes & Security

**Security:**
- Password hashing via Werkzeug
- CSRF protection on all forms
- API token authentication for `/api/v1` with optional scopes
- Server-side feature flag and module enforcement (disabled modules block routes AND APIs)
- Role-based authorization decorators (admin, staff, api_only)
- Secure file uploads: extension allowlist, file-signature verification, size limits, safe filenames, admin-only sensitive uploads
- No card data storage — no card number, CVV, or expiration fields anywhere in the system
- Production config validates that `SECRET_KEY` and `ADMIN_PASSWORD` are not defaults
- Rate limiting on login (5 attempts/60s) and API auth (60 attempts/60s), configurable via Redis-backed limits in production
- Security headers enforced (CSP, HSTS, X-Frame-Options, etc.)

**Audit Logging:**
- Dedicated FastAPI microservice (`services/audit-log/`) with PostgreSQL persistence
- All event payloads are hash-chained for tamper evidence
- Idempotent event recording (deduplication by idempotency key)
- Configurable fail-closed behavior for critical financial actions
- 60+ audit event types covering auth, POS, receipts, inventory, orders, custom requests, markets, feature flags, settings, API tokens, and more

**Data Integrity:**
- UTC timestamps throughout
- `Numeric(10, 2)` for all monetary values — zero floating-point money
- Soft-delete/archival pattern for important business records
- Comprehensive database indexes on slugs, SKUs, statuses, order/receipt numbers, customer emails, market dates, and token hashes
- Transactional integrity for POS sales (order + payment + inventory deduction in a single atomic operation)

**Design System:**
- Centralized design tokens in `DESIGN.md` — no hardcoded colors in templates
- Shared Jinja components for buttons, forms, badges, tables, cards, alerts, pagination
- Distinct visual densities: warm/polished public site, dense/data-rich admin, touch-first POS
- WCAG 2.2 AA compliance target: keyboard navigation, focus management, ARIA labels, color contrast, `prefers-reduced-motion`, 320px viewport support
- HTMX for scoped server interactions; Alpine.js limited to tiny UI behaviors

---

### 7. Testing Strategy

**623 tests** across 36 test files (~13,200 lines of test code), covering:

| Test File | Coverage Area |
|---|---|
| `test_phase0_data_model.py` | Model creation, Business foundation, feature flags |
| `test_phase1_launch_gate.py` | App factory, auth gates, role permissions |
| `test_phase2_catalog.py` | Products, variants, categories, collections |
| `test_phase3_cost_engine.py` | Cost calculations, suggested pricing, margins |
| `test_phase4_pos.py` | POS session lifecycle, cash sales, inventory deduction, refund, closeout |
| `test_phase4_ux.py` | Public storefront pages, custom order forms |
| `test_phase5_markets_expenses.py` | Market planning, receipts, expense ledger |
| `test_phase6_analytics.py` | Executive summary, analytics insights, Chart.js data |
| `test_receipts.py` | Receipt upload, AI parsing mock, approval → ledger entries, audit dispatch |
| `test_auth.py` | Login/logout, failed login auditing, password hashing |
| `test_api_tokens.py` | Token creation/revocation, scope enforcement |
| `test_security_config.py` | Production config validation, rate limits, security headers |
| `test_alignment_pass.py` | Module registry, feature flag enforcement, disabled module blocking |
| `test_foundation_hardening.py` | Audit dispatch, POS tamper protection, API workflow guards |
| `test_trend_scout.py` | AI trend detection, scoring, backtesting |
| `test_milestone4_product_ops.py` | Product readiness, launch checklists, dead-stock recommendations |
| `test_milestone5_printer_reliability.py` | Failure autopsy, reliability scoring |
| `test_milestone7_booth_mode.py` | Break-even tracking, sales pace, action hints |
| `test_model_analysis_*` (4 files) | 3D model analysis pipeline, slicer client, artifact persistence |
| `test_public_storefront.py` | Public pages, checkout, pickup scheduling |
| `test_report_studio.py` | Centralized reporting, heat maps, CSV exports |
| `test_promotion.py` | Social content queue, sign generation |
| `test_pmp.py` | Project management (milestones, phases) |
| `test_openapi_spec.py` | API spec validation |
| `test_rate_limiting.py` | Login and API auth rate limiting |
| `test_settings.py` | Application settings, themes, module status |

Key testing principles:
- Service-layer testing over incidental UI-only tests
- Cross-module workflows tested where bugs would be expensive
- AI-dependent paths are mocked; code must work with AI disabled
- Audit dispatch is verified for critical workflows
- Upload validation rejects spoofed extensions and unsafe files
- No card data fields exist in any POS form or API schema (verified by test)

---

### 8. Containerization & Deployment

**Docker Compose** orchestrates the full stack:

```yaml
# Services:
# - db (PostgreSQL 17 with health checks)
# - redis (session/broker/caching)
# - seaweedfs (S3-compatible object storage)
# - audit-log (FastAPI microservice, port 8090)
# - intelligence (FastAPI microservice, port 8091)
# - slicer (FastAPI microservice, port 8092)
# - web (Flask app, port 5000)
# - worker (Celery background jobs)
# - beat (Periodic task scheduler)
```

**Dockerfile** (multi-stage):
- Stage 1 (`assets`): Node.js builds Tailwind CSS from Jinja template scanning
- Stage 2 (`base`): uv installs dependencies, non-root `appuser`
- Stage 3 (`dev`): Adds dev dependencies for local development
- Production runs `gunicorn` as non-root with compiled bytecode

**Deployment workflow:**
1. `docker compose --profile build build slicer-base` (builds the slicer base image with Bambu Studio)
2. `docker compose --profile build up --build -d` (builds slicer, then web app image)
3. `docker compose --profile release run --rm migrate` (runs Alembic migrations)
4. `docker compose up -d web worker beat audit-log` (starts application services)

---

### 9. Code Metrics

| Metric | Count |
|---|---|
| **Main app Python lines** | ~41,800 |
| **Models** | 28 model files, ~3,160 lines |
| **Services (business logic)** | 45+ service files, ~18,500 lines |
| **Blueprints (routes)** | 27 blueprint modules, ~13,200 lines |
| **HTML Templates** | 128 templates, ~11,300 lines |
| **Forms (WTForms)** | 20 files, ~2,300 lines |
| **API Schemas (Marshmallow)** | 18 files, ~950 lines |
| **Unit/Integration Tests** | 36 files, ~13,200 lines (623 tests) |
| **Microservices (Python)** | 4 services, ~14,700 lines |
| **Migrations** | 6 Alembic migration scripts |
| **Modules in registry** | 22+ |
| **API endpoints** | 50+ (auto-documented via OpenAPI) |

---

### 10. What Makes This Different

**Operational intelligence, not just CRUD:** The system's value isn't in storing data — it's in answering "what should we make, sell, restock, stop selling, improve, or prepare next?" Every module feeds into this question: the Cost Engine provides true profitability, Analytics surfaces velocity and margin, Prep Tasks generate market-specific to-do lists, Trend Scout identifies emerging opportunities, and Booth Mode tracks live market performance against break-even.

**Modular monolith with safe runtime toggles:** 22+ modules are individually enableable/disableable via database-backed feature flags with full server-side enforcement. Disabling a module hides it from navigation, blocks all routes, and returns 404 on API endpoints — never relying on UI hiding as security.

**Audit-first financial integrity:** Every meaningful business action (POS sales, receipt approvals, inventory deductions, price changes, refund) dispatches a structured audit event to a separate FastAPI microservice with hash-chained, idempotent event storage. Critical financial actions can be configured to fail-closed if audit delivery is unavailable.

**Design system discipline:** Public, admin, and POS interfaces share one cohesive design language via CSS custom properties and Tailwind — warm storefront, compact admin, touch-first POS — with no hardcoded colors and full WCAG 2.2 AA compliance.

**AI as suggestion, never authority:** ChatGPT/Ollama integrations are limited to receipt parsing drafts, trend detection, and analytics insights — all behind explicit feature flags, always requiring human review, and with full fallback paths when AI is disabled.

---

### 11. How to Run Locally

```bash
# Prerequisites: Python 3.14, uv, Node.js, Docker

# 1. Install dependencies
uv python install 3.14
uv sync
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env with local values

# 3. Start services (database, redis, object storage, audit-log)
docker compose up -d

# 4. Run migrations
uv run flask --app app:create_app db upgrade

# 5. Seed data
uv run flask --app app:create_app seed demo

# 6. Build Tailwind CSS
npm run build:css

# 7. Start the development server
uv run flask --app app:create_app run --debug
```

Open `http://localhost:5000` in a browser. Staff login at `/staff/login`. Admin dashboard at `/admin`. POS at `/pos`. API docs at `/api/docs`.

**Testing:**
```bash
uv run pytest --tb=short -q
```

---

### 12. Status & Evolution

The system is a continuously evolving foundation following a phased milestone approach (Phase 0-6 + milestones). The production-readiness scorecard in `docs/production_readiness_scorecard.md` tracks 15 areas (POS, Inventory, Markets, Receipts, Analytics, Cost Engine, Prep Tasks, Module Registry, Audit Logging, Security, REST API, Database, Tests, Docker, Documentation, SaaS Readiness) with scores ranging from 6–8 out of 10, with ongoing gaps documented including partial refunds, deeper API scoping, and MariaDB-specific SQL compatibility for certain Report Studio queries.

The system is structured for SaaS-later readiness: a `Business` model with nullable `business_id` fields on all major records provides the future multi-tenant foundation without the complexity of full tenant isolation today.
