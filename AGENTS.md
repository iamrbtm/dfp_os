# AGENTS.md

## Project

Dude Fish OS / DFPos is the Flask-based operating system, private admin dashboard, mobile-friendly POS, public website, REST API, analytics platform, and operations hub for Dude Fish Printing.

Dude Fish Printing is a family-run 3D printing business relocating to the Clarksville, Tennessee area.

This is a fresh rebuild. Do not preserve old architecture unless specifically asked. Build a clean, production-minded Flask app with a public website, private admin dashboard, mobile-friendly POS, full REST API, analytics, receipt workflow, cost engine, market prep engine, feature flags, and containerized deployment.

The software should be useful for Dude Fish Printing now and structured so it could become a paid service later.

The app should answer this core question:

> What should Dude Fish Printing make, sell, restock, stop selling, improve, or prepare next?

## Business Context

Dude Fish Printing sells online, through Facebook, at vendor markets, through word of mouth, through custom orders, and eventually through local Clarksville-area business outreach.

Important product lanes:

- Dragons
- Fidgets
- Flexi animals
- Personalized gifts
- Clarksville/Tennessee-themed products
- Military-family-safe gifts
- Vendor market impulse items
- Custom orders
- Small business display products
- Light manufacturing / practical printed parts

Clarksville has a strong military-family presence. The app may support military-family-safe products, but do not assume the business has rights to official military logos, unit insignia, installation marks, university marks, copyrighted characters, or trademarked designs. Build license/compliance tracking into product/model records.

Current printer fleet to seed:

- 4 Bambu A1 printers
- 2 Bambu X1 Carbon printers, one broken
- 2 Bambu P1P printers
- 4 AMS Lite units
- 1 standard Bambu AMS/multicolor unit

## Design Source of Truth

`DESIGN.md` is the design source of truth for the public website, admin dashboard, POS, and shared component system.

The Figma Make public website screenshots define the visual language for the entire product:

-   warm off-white page backgrounds
-   coral/orange primary actions
-   teal secondary actions
-   deep navy hero and emphasis sections
-   rounded cards
-   soft borders
-   friendly forms
-   pill filters
-   clear CTAs
-   clean typography
-   dark footer/support sections
-   generous whitespace on public pages
-   tighter task-focused layouts on admin/POS pages

Do not treat the admin dashboard or POS as a separate generic admin template. They should feel like the same DudeFish/DFPos product family, but tuned for faster internal work.

Public pages should feel warm, polished, friendly, and trustworthy.

Admin pages should feel clean, fast, practical, data-rich, and calm.

POS pages should feel touch-friendly, fast, market-ready, and almost impossible to mess up during a rush.

Use `DESIGN.md` for:

-   colors
-   design tokens
-   spacing
-   typography
-   buttons
-   cards
-   tables
-   forms
-   layout density
-   navigation patterns
-   responsive behavior
-   loading states
-   empty states
-   error states
-   accessibility rules
-   public/admin/POS visual consistency

Do not hardcode colors. Use design tokens.

Do not invent fake reviews, fake testimonials, fake customer counts, fake market locations, fake policies, fake analytics, fake sales, or fake business claims.

Demo data is allowed only when clearly marked as demo or placeholder data.

## Product Direction

DFPos is not just a POS. It is the operating cockpit for a small product-based business.

The foundation must connect:

1. POS
2. Inventory
3. Vendor markets
4. Receipts & Expenses
5. Analytics
6. Cost Engine
7. Prep Tasks / Market Prep
8. Custom orders
9. Print jobs
10. Audit logging
11. REST API
12. Feature flags and module registry
13. Business/account foundation for future SaaS readiness

The secret sauce is not AI alone. The value comes from clean operational data, accurate cost/profit math, useful workflows, and smart recommendations.

## Required Stack

Use:

- Python 3.14
- uv for Python version management, dependency management, locking, and running commands
- Flask
- Jinja2 templates
- MariaDB
- SQLAlchemy ORM
- Flask-Migrate / Alembic
- Flask-Login
- Flask-WTF / WTForms
- Tailwind CSS
- Vanilla JavaScript
- HTMX where useful
- Alpine.js only for small UI interactions
- Chart.js for analytics
- Flask-Smorest or Flask-RESTX for API/OpenAPI
- Marshmallow or Pydantic for API schemas
- Docker and Docker Compose
- Gunicorn
- Pytest
- Ruff and/or Black
- python-dotenv
- PyMySQL

A small Node/npm toolchain is allowed only for Tailwind.

A small Preact + TypeScript + Vite island is allowed only for the `/pos` checkout experience if it clearly improves speed, reliability, and maintainability. Flask must remain the backend and API provider.

Do not make this a Node-first app.

Do not use:

- React for the whole app
- Next.js
- Vue
- Angular
- Prisma
- Express
- SPA architecture for the admin/public site
- A separate Node backend

## Python and uv Rules

Use Python 3.14 as the target runtime.

Required files:

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.env.example`

`.python-version` must contain:

```text
3.14
```

Use `uv` for dependency management and command execution.

Preferred commands:

```bash
uv python install 3.14
uv python pin 3.14
uv init --app --python 3.14
uv add flask sqlalchemy flask-sqlalchemy flask-migrate pymysql flask-login flask-wtf email-validator python-dotenv flask-smorest marshmallow gunicorn click rich
uv add --dev pytest pytest-cov ruff black
uv lock
uv run flask --app app:create_app db upgrade
uv run pytest
```

Do not create `requirements.txt` as the source of truth. If a `requirements.txt` export is later needed for a host, generate it from the locked uv environment and document that it is derived.

Python 3.14 compatibility is mandatory. After dependencies are selected, run `uv lock` and `uv run pytest`. If any dependency does not resolve or run under Python 3.14, replace it with a compatible alternative before continuing.

Avoid unnecessary compiled dependencies. Prefer libraries that publish Python 3.14-compatible wheels or are pure Python.

## Workflow And Architecture Docs

Use the project docs together instead of overloading this file:

- `PROMPTS.md`: session workflow, custom prompts, and agent rules of engagement
- `TODO.md`: live working list that agents should keep updated
- `DESIGN.md`: product vision, UX direction, and business-facing design intent
- `ARCHITECTURE.md`: folder structure, data flow, state choices, and module/service interaction rules

Core architectural expectations still apply:

Put business logic in services.

Put browser validation in forms.

Put API validation/serialization in schemas.

Use reusable Jinja components/partials.

Use a pragmatic internal module registry. Do not build true external plugins, a plugin marketplace, or separate microservices for core modules.

Expected structure:

```text
app/
  __init__.py
  config.py
  extensions.py
  cli.py
  module_registry.py
  models/
  blueprints/
    public/
    auth/
    dashboard/
    products/
    inventory/
    printers/
    print_jobs/
    customers/
    orders/
    custom_orders/
    markets/
    receipts/
    expense_ledger/
    analytics/
    cost_engine/
    prep_tasks/
    pos/
    api/
    settings/
  forms/
  schemas/
  services/
  templates/
  static/
    src/
    dist/
  utils/
migrations/
tests/
scripts/
docs/
uploads/.gitkeep
services/
  audit-log/
.env.example
.gitignore
Dockerfile
docker-compose.yml
pyproject.toml
uv.lock
.python-version
package.json
tailwind.config.js
postcss.config.js
README.md
AGENTS.md
DESIGN.md
```

## Module Registry and Feature Flags

DFPos must be built as a modular monolith.

Each core module should be self-contained enough to maintain, test, document, and disable later.

Each module should declare:

- key
- display name
- description
- feature flag key
- default enabled state
- dependencies
- blueprint names
- admin nav entries
- POS nav entries if relevant
- API resources if relevant
- required roles/permissions
- health check function
- docs location

Required module keys:

- `public_site`
- `auth`
- `dashboard`
- `products`
- `inventory`
- `printers`
- `print_jobs`
- `customers`
- `orders`
- `custom_orders`
- `pos`
- `markets`
- `receipts`
- `expense_ledger`
- `analytics`
- `cost_engine`
- `prep_tasks`
- `api`
- `settings`
- `audit_logs`
- `feature_flags`

Feature flags must support:

- `.env` / config defaults
- database overrides through Settings or FeatureFlag records
- admin-visible module status
- route enforcement
- API enforcement
- navigation hiding/locking
- permission enforcement

Disabled modules should:

- be hidden from staff/helper users
- show as locked/unavailable to admins where useful
- block protected routes
- block protected API endpoints
- avoid relying on UI hiding as security

Do not build subscriptions or billing yet.

## Business / Account Foundation

Build a lightweight Business or Account foundation now so the app can become SaaS-ready later.

Rules:

- Seed one default business/account for Dude Fish Printing.
- Add `business_id` or `account_id` to business records where appropriate.
- Keep the app single-business by default.
- Avoid full multi-tenant complexity unless explicitly asked.
- Do not build billing, subscriptions, or plan management yet.
- Make sure feature flags can eventually be scoped by business/account.

## Security Rules

Never hardcode secrets.

Never commit `.env`.

Never commit real DB credentials, API keys, production secrets, or card data.

Use `.env.example` placeholders only. The real `.env` is local-only and must never be committed.

Required `.env.example` values include:

```env
FLASK_ENV=development
SECRET_KEY=change-me
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/dudefish_os
APP_NAME=Dude Fish OS
APP_BASE_URL=http://localhost:5000
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me-now
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH_MB=16

POS_CARD_PROCESSING_ENABLED=false
POS_CARD_PROCESSOR=placeholder

AUDIT_LOG_BASE_URL=http://localhost:8090
AUDIT_LOG_TOKEN=change-me-in-production
AUDIT_LOG_ENABLED=true
AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS=true

OPENAI_API_KEY=
OPENAI_MODEL_RECEIPTS=gpt-5.5
OPENAI_MODEL_ANALYTICS=gpt-5.5
AI_RECEIPT_PARSING_ENABLED=false
AI_ANALYTICS_INSIGHTS_ENABLED=false
```

The repository may include a local starter `.env` only when the user explicitly requests it. If present, `.env` must be listed in `.gitignore` and treated as local machine configuration, not project documentation.

Implement:

- Password hashing
- Login/logout
- Role-based authorization
- CSRF protection
- API token auth for `/api/v1`
- Optional API scopes where practical
- Secure file uploads
- Safe filenames
- Upload size limits
- Extension allowlist
- Admin-only access for sensitive uploads
- Friendly 403/404/500 pages
- Audit logs for meaningful actions
- Server-side module/feature flag enforcement
- No real card processing yet
- No card number fields
- No CVV fields
- No card data storage

## Audit Logging

All important actions must be recorded through the audit-log microservice.

Do not write audit events directly to the Flask app's main database unless a read-only viewer/cache pattern is explicitly documented. The source of truth for audit events is the dedicated audit-log service.

Basically:

> If it happens in the program, it needs to be logged.

### Microservice Location

```text
services/audit-log/
```

- Stack: FastAPI + PostgreSQL 17 + SQLAlchemy 2.x async + Redis streams optional
- Port: `8090`
- API base: `/api/v1/`
- Auth: Bearer token via `Authorization` header

### Setup

```bash
cd services/audit-log
cp .env.example .env
# Edit .env with real secrets
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8090
```

Required `.env` vars for the microservice:

```env
AUDIT_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/audit_log
AUDIT_INTERNAL_API_TOKEN=generate-a-secure-token
AUDIT_HASH_SECRET=generate-a-secure-hmac-key
```

### Flask App Configuration

Add these to `.env` and `config.py`:

```env
AUDIT_LOG_BASE_URL=http://localhost:8090
AUDIT_LOG_TOKEN=the-same-token-from-above
AUDIT_LOG_ENABLED=true
AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS=true
```

### Usage

Import and use the client in any service or blueprint. Prefer service layer logging.

```python
from app.services.audit_client import get_audit_client

client = get_audit_client()
client.record(
    action="product.created",
    entity_type="product",
    entity_id=str(product.id),
    actor_id=str(current_user.id),
    actor_type="user",
    actor_display_name=current_user.display_name,
    source_module=__name__,
    before_state=None,
    after_state={"name": product.name, "price": str(product.price)},
    metadata={"request_id": g.request_id},
)
```

### Required Audit Events

At minimum log:

- login
- logout
- failed login
- password change
- role change
- user created
- user updated
- user deactivated
- API token created
- API token revoked
- settings changed
- feature flag changed
- module enabled/disabled
- product created/updated/archived/restored
- variant created/updated/archived/restored
- inventory adjustment
- inventory transfer
- inventory deduction
- inventory reservation
- inventory release
- filament spool created/updated/archived
- print job created/updated/status changed/failed/completed
- customer created/updated/archived
- custom request created/updated/status changed/converted
- order created/updated/status changed/canceled/refunded
- payment recorded/updated/voided/refunded
- POS session opened/closed/voided
- POS sale completed/voided/refunded
- receipt uploaded
- receipt parsed by AI
- receipt manually edited
- receipt approved
- receipt rejected
- receipt archived
- expense ledger entry created/updated/deleted/archived
- market created/updated/status changed/completed
- market financial fields changed
- market packing list created/updated
- prep task generated/updated/completed/reopened
- analytics AI insight generated
- CSV import
- CSV export
- file upload
- failed authorization
- disabled module access attempt
- admin action
- destructive action

### Audit Event Rules

- Use clear dotted past-tense actions, such as `receipt.approved`, `pos_sale.completed`, `inventory.adjusted`.
- Include `before_state` and `after_state` for updates.
- Include `actor_id`, `actor_type`, and `actor_display_name`.
- Include `source_module`.
- Include request ID, IP, and user agent when available.
- Include `business_id` or `account_id` where applicable.
- Log in the service layer, not templates.
- Audit failures should not silently disappear. Log warnings/errors locally.
- For critical financial actions, prefer failing closed if audit logging cannot dispatch unless config explicitly allows non-blocking mode.
- Add tests that verify audit dispatch for key workflows.

## Database Rules

Use MariaDB as the main database.

Use SQLAlchemy models and Flask-Migrate migrations.

Every table should include:

- id
- created_at
- updated_at

Use soft delete/archival for important business records where practical.

Use UTC timestamps.

Use `Numeric(10, 2)` or integer cents for money. Do not use floats for money.

Add indexes for common filters/searches:

- business/account IDs
- slugs
- SKUs
- statuses
- order numbers
- receipt numbers
- customer email
- market date
- print job status
- inventory location
- API token hashes
- feature flag keys

Since there is no live production data, schema reset and migration rebuilds are allowed when they produce a better foundation. Document destructive database changes clearly.

## UX Rules

Build for real daily use by a small business owner, market vendor, cashier, or helper.

The app must be responsive, clean, quick, and forgiving.

The public website must follow the visual direction in `DESIGN.md` and should feel warm, colorful, family-friendly, polished, and trustworthy.

The admin dashboard must carry the same design system, but with denser layouts, stronger tables, faster scanning, and fewer marketing-style sections.

The POS must be comfortable on a phone, tablet, or laptop at a vendor market. It should prioritize speed over decoration.

Use Tailwind CSS throughout.

Use shared Jinja components/partials where practical.

Use HTMX for inline updates when helpful, including:

-   POS cart updates
-   print job status changes
-   quick inventory adjustments
-   prep task completion
-   receipt review
-   admin table filters
-   small status updates

Use Alpine.js only for small UI interactions.

Do not create a full SPA for the public site or admin dashboard.

Forms need:

-   clear labels
-   helpful helper text
-   validation
-   empty states
-   flash messages
-   cancel/back buttons
-   confirmation for destructive actions
-   friendly errors
-   accessible focus states

Admin tables need:

-   search
-   filters
-   sortable columns where practical
-   status pills
-   bulk actions where safe
-   empty states
-   clear row actions
-   pagination when needed

All dynamic pages must include loading, empty, error, success, and validation states where relevant.

Do not ship screens that only work with happy-path data.

## Required Modules

Build these modules:

1. Public website
2. Authentication and roles
3. Business/account foundation
4. Admin dashboard
5. Feature flags / module registry
6. Products
7. Categories
8. Collections
9. Product Studio / SKU-based product records
10. Product design, model file, and license tracking
11. Printer fleet
12. AMS / multicolor unit tracking
13. Filament/material inventory
14. Finished goods inventory
15. Inventory movements
16. Print job queue
17. Failed print tracking
18. Customers
19. Custom order requests
20. Orders, order items, payments
21. POS system
22. Vendor markets
23. Market packing lists
24. Market sales
25. Receipts & Expenses
26. Expense ledger
27. Cost Engine
28. Prep Tasks / Market Prep
29. Analytics
30. API tokens
31. Full REST API
32. CSV import/export
33. Settings
34. Audit logs viewer/proxy if appropriate

## Receipts & Expenses Requirements

The visible user-facing module should be named `Receipts & Expenses`.

Receipts are the main workflow. Expense ledger entries are the structured accounting result.

Required receipt workflow:

1. Upload or create receipt.
2. Store receipt file securely.
3. Extract or manually enter:
   - vendor
   - purchase date
   - subtotal
   - tax
   - fees
   - tip if any
   - total
   - payment method
   - line items
   - notes
   - related market/order/product/inventory item where applicable
4. Use ChatGPT integration for receipt parsing assistance when enabled.
5. Always require manual review before extracted receipt data is approved.
6. Approved receipt creates or updates structured ExpenseLedger entries.
7. Receipt line items can allocate cost to:
   - filament/materials
   - tools
   - printer parts
   - booth fees
   - packaging
   - shipping
   - advertising
   - software
   - licenses/fees
   - travel/vehicle
   - office supplies
   - specific market
   - specific order
   - inventory
   - general business
8. Tax and fees must be allocatable across line items.
9. Support duplicate detection.
10. Support receipt statuses:
   - uploaded
   - extracted
   - needs_review
   - approved
   - rejected
   - archived

Receipt AI rules:

- AI output is a draft/suggestion only.
- Never write AI-extracted values directly into final ledger entries without human approval.
- Code must work with AI disabled.
- Manual receipt entry must always work.
- Store AI confidence if practical.
- Audit receipt upload, AI parse, manual edit, approval, rejection, and archive.

## Cost Engine Requirements

Cost Engine is a first-class service/module.

It should calculate and expose:

- material cost
- filament grams
- cost per gram
- labor minutes
- labor rate
- print time
- machine/depreciation estimate if configured
- packaging cost
- card/payment fees
- market/booth allocation where relevant
- failed print/failure-rate adjustment
- suggested price
- margin dollars
- margin percent
- profit per product
- profit per order
- profit per POS sale
- profit per market
- profit per custom order

Cost Engine should be used by:

- Products
- Variants
- Print Jobs
- POS
- Orders
- Markets
- Receipts & Expenses
- Analytics
- Prep Tasks

Use Decimal/Numeric/integer cents. Do not use floats for money.

## Prep Tasks / Market Prep Requirements

Prep Tasks / Market Prep is a first-class service/module.

The system should support:

- reusable prep task templates
- generated prep tasks for upcoming markets
- packing list generation
- suggested quantities to bring
- inventory gap detection
- suggested reprints
- supply checklist
- cash box checklist
- signage/payment-device checklist
- staff/helper assignment if users exist
- due dates
- completed/incomplete status
- market readiness score
- “What should I bring?” summary

Market Prep should use:

- upcoming market details
- previous market sales
- product sell-through
- inventory levels
- reorder targets
- print job queue
- production capacity
- cost/margin data
- packing list history

## ChatGPT Integration Rules

Use ChatGPT only for:

1. Receipt parsing assistance.
2. Analytics explanations and business insights.

Do not add broad AI features without explicit request.

Required configuration placeholders:

```env
OPENAI_API_KEY=
OPENAI_MODEL_RECEIPTS=gpt-5.5
OPENAI_MODEL_ANALYTICS=gpt-5.5
AI_RECEIPT_PARSING_ENABLED=false
AI_ANALYTICS_INSIGHTS_ENABLED=false
```

Rules:

- Do not commit API keys.
- Code must work with AI disabled.
- Receipt parsing must fall back to manual entry.
- Analytics insights must fall back to normal charts/summaries.
- Store AI outputs as suggestions/drafts.
- Do not send unnecessary sensitive data to AI.
- Keep prompts centralized in services, not scattered in routes or templates.
- Audit AI-assisted receipt parsing and analytics insight generation.

## POS Requirements

The POS is a first-class feature.

Route namespace:

```text
/pos
```

It must work on mobile, tablet, laptop, and desktop.

Required POS features:

- Open POS session
- Close POS session
- Select active market/event
- Select inventory location, such as Market Bin
- Square-style product tile buttons
- Category tabs
- Search
- Cart panel/drawer
- Quantity controls
- Remove line item
- Add custom item with manual description and price
- Add custom order deposit
- Quick customer create
- Optional customer link
- Cash checkout
- Change due calculation
- External card placeholder
- Venmo/Cash App/Apple Pay/Other payment recording
- Receipt/confirmation page
- Inventory deduction
- Order/payment record creation
- Market attribution
- POS session summary
- End-of-day cash/payment totals
- Void/refund support where practical
- Audit logging for all meaningful POS actions

Custom orders must be included in POS:

- Create custom request from POS
- Collect custom order deposit
- Link deposit to order/payment/custom request
- Add internal notes

Card rules:

- No real card processing yet
- No card number fields
- No CVV fields
- No card data storage
- Leave service boundary for future Square/Stripe integration

## POS Frontend Rules

The POS must be optimized for fast checkout on mobile, tablet, and laptop during busy vendor markets.

Default approach:

- Flask route renders the POS shell.
- POS uses API endpoints for products, cart actions, sale completion, inventory deduction, and session closeout.
- Use large touch targets, minimal typing, and fast product search.

Allowed implementation options:

1. Jinja + HTMX + Alpine.js if the workflow stays fast and simple.
2. A small Preact + TypeScript + Vite island mounted only on `/pos` if a client-side cart is cleaner and faster.

If using Preact for POS:

- Keep it inside `app/static/pos/` or a clearly named frontend source folder.
- Use Flask as the backend and API provider.
- Do not add a separate Node backend.
- Do not make the admin dashboard or public site a SPA.
- Build assets into Flask static files.
- Keep card processing as a placeholder only.

## Public Website Pages

Build public pages that follow `DESIGN.md` and the Figma-derived public website direction.

Required public pages:

-   Home
-   Shop
-   Product listing/category pages
-   Product detail pages
-   Cart
-   Checkout
-   Order confirmation
-   Custom Orders
-   Markets & Events
-   Gallery
-   About
-   Learn / What Is 3D Printing?
-   Materials & Options, if separated from Learn
-   FAQ & Policies
-   Contact
-   Privacy Policy placeholder
-   Terms placeholder
-   Accessibility placeholder
-   Shipping Policy placeholder
-   Return/Refund Policy placeholder

The public website should support:

-   ready-made product browsing
-   product search/filtering
-   product detail pages
-   custom order intake
-   file/image upload for custom requests
-   market/event discovery
-   gallery browsing
-   customer education
-   contact form submission
-   checkout flow when ecommerce is enabled
-   public content managed through admin pages where practical

Do not invent final policy language. Use clearly marked placeholders until real business policies are provided.

Do not create fake testimonials, fake reviews, fake market history, fake customer numbers, or unsupported shipping claims.

## Admin Pages

Build CRUD/list/detail pages for:

- Business/account settings
- Feature flags/module registry
- Products
- Categories
- Collections
- Variants
- Model assets/licenses
- Printers
- AMS units
- Filament spools
- Inventory locations
- Inventory
- Inventory movements
- Print jobs
- Customers
- Orders
- Custom order requests
- POS sessions
- POS sales
- Markets
- Market packing lists
- Market sales
- Receipts
- Expense ledger entries
- Cost Engine settings/calculators
- Prep task templates
- Prep tasks
- Analytics
- API tokens
- Settings
- Users
- Audit logs viewer/proxy if appropriate

CRUD means list, detail, create, edit, archive/delete where appropriate, search/filter where practical, validation, flash messages, API support where required, and audit logging.

## API Requirements

Build full REST API under:

```text
/api/v1/
```

Requirements:

- Token authentication
- JSON responses
- Pagination
- Filtering where practical
- Sorting where practical
- Search where practical
- OpenAPI documentation
- Consistent error format
- CSV export endpoints
- Feature flag enforcement
- Permission enforcement
- Audit logging for create/update/delete/import/export where appropriate

Required API resources:

- businesses/accounts
- feature-flags/modules
- products
- categories
- collections
- printers
- ams-units
- filament-spools
- inventory
- inventory-movements
- print-jobs
- customers
- orders
- order-items
- payments
- custom-requests
- markets
- market-packing-lists
- market-sales
- pos-sessions
- pos-sales
- receipts
- receipt-line-items
- expense-ledger
- cost-engine
- prep-task-templates
- prep-tasks
- analytics
- api-tokens
- settings

Do not expose password hashes, token hashes, or sensitive fields.

## Analytics Requirements

Analytics must answer:

- What products sell best?
- What products are most profitable?
- What should be printed before the next market?
- Which products are sitting too long?
- Which markets are worth repeating?
- Which channels perform best?
- Which printer has the highest failure rate?
- Which printer is most productive?
- What filament is low?
- What custom orders are due soon?
- What expenses are reducing margin?
- Which receipts need review?
- How much cash should be in the drawer after a POS session?
- What payment methods were used at a market?
- What items sold through POS versus custom/online orders?
- What should be brought to the next market?

Use Chart.js for visual analytics.

ChatGPT analytics insights are allowed only when enabled and must be backed by real numbers already shown in the UI.

## Seed Data

Create:

```bash
flask seed demo
```

Seed:

- Default business/account
- Admin user
- Staff user
- Categories
- Collections
- Demo products
- Variants
- Model assets/licenses
- Printer fleet
- AMS units
- Filament spools
- Inventory locations
- Demo inventory
- Demo inventory movements
- Demo customers
- Demo custom orders
- Demo market
- Demo market packing list
- Demo POS session
- Demo receipt
- Demo expense ledger entries
- Demo prep tasks
- Demo feature flags

Demo products:

- Rainbow Dragon
- Small Articulated Dragon
- Mystery Dragon Egg
- Fidget Slider
- Flexi Turtle
- Flexi Axolotl
- Clarksville TN Magnet
- Tennessee Ornament
- Custom Name Keychain
- QR Code Counter Sign
- Business Card Holder
- Vendor Price Tag Stand
- Custom Order Deposit

## Testing Rules

Use Pytest.

At minimum test:

- App factory creates app
- Home page loads
- Login page loads
- Admin requires login
- Admin user can log in
- Role permissions work
- Feature flag disables route access
- Feature flag disables API access
- Product model can be created
- Product admin list loads
- Product API requires token
- Product API returns data with token
- POS page requires auth
- POS can open session
- POS can create a cash sale
- POS sale creates order/payment records
- POS sale deducts inventory
- POS closeout calculates expected cash
- Receipt upload works
- Receipt manual entry works
- Receipt AI parse is mocked and creates draft extraction
- Receipt approval creates expense ledger entries
- Receipt edit dispatches audit event
- Cost Engine calculates expected values
- Market packing list works
- Prep task generation works
- Market profitability works
- Custom request public form validates
- CSV export returns a file response
- Analytics summary returns expected keys
- Analytics AI insight is mocked
- Audit dispatch is called for key workflows
- Upload validation rejects unsafe files
- No card data fields exist in POS forms/API

## GitHub Workflow

Use the issue templates in `.github/ISSUE_TEMPLATE/` for filing bugs, features, and tasks. Use module labels (`module:pos`, `module:analytics`, etc.) and priority labels when creating issues. Reference issues in commits and PRs with `#123`.

Before pushing, always run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -v --tb=long
```

The CI workflow (`.github/workflows/ci.yml`) runs lint + tests on every push to `main` and PR branches.

## Build Behavior for Codex

When asked to build:

1. Read `AGENTS.md`
2. Read `DESIGN.md`
3. Inspect repo files
4. Give a short implementation plan
5. Build one phase at a time unless explicitly asked to do a full pass
6. Run formatting/tests if possible
7. Summarize changed files
8. Explain how to run the app
9. Stop at requested phase

When asked for a production-readiness pass:

1. Inspect the repo.
2. Update docs first if needed.
3. Create or update the module registry / feature flags foundation.
4. Add or refactor the Business/Account foundation.
5. Harden the core modules.
6. Add/repair audit logging.
7. Add/repair tests.
8. Create or update `docs/production_readiness_scorecard.md`.
9. Run checks/tests.
10. Report exactly what changed and what remains.

Do not build all unrelated features in one giant pass unless explicitly requested.

## Production Readiness Scorecard

For major readiness passes, create or update:

```text
docs/production_readiness_scorecard.md
```

Score these areas from 0-10:

- POS
- Inventory
- Markets
- Receipts & Expenses
- Analytics
- Cost Engine
- Prep Tasks
- Module Registry / Feature Flags
- Audit Logging
- Security / Permissions
- REST API
- Database / Migrations
- Tests
- Docker / Deployment
- Documentation
- SaaS-Later Readiness

Include:

- current status
- bugs found
- missing features
- fixes made
- remaining risks
- tests added
- next recommended step

## Definition of Done

A feature is done only when:

- It has models if persistent
- It has migrations if schema changes
- It has forms/schemas if it accepts input
- It has admin pages where needed
- It has API endpoints where required
- It has validation
- It has error handling
- It has user feedback
- It has feature flag enforcement where relevant
- It has permission enforcement
- It has audit logging for meaningful actions
- It has tests where practical
- It works in Docker or documents environment limitations
- It is documented
- It has no hardcoded secrets
- It does not store card data

The foundation is production-ready when:

- AGENTS.md and DESIGN.md reflect the architecture.
- The core modules are production-minded and wired together.
- Feature flags can enable/disable modules safely.
- Business/Account foundation exists.
- POS can run a reliable cash sale.
- Inventory deducts correctly.
- Receipts can be uploaded, reviewed, approved, and converted to ledger entries.
- ChatGPT receipt parsing is optional and manually reviewed.
- ChatGPT analytics insights are optional and backed by real numbers.
- Cost Engine is reusable and tested.
- Prep Tasks / Market Prep is reusable and tested.
- Market profitability works.
- Audit logging is dispatched for all meaningful actions.
- Security checks are enforced.
- API endpoints are protected and documented.
- Tests cover critical workflows.
- Docker and uv workflow are documented.
- `docs/production_readiness_scorecard.md` exists.
- README explains how to run, test, seed, and develop the app.
- It follows `DESIGN.md` design tokens, spacing, component behavior, accessibility rules, and public/admin/POS visual consistency requirements.
