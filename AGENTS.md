# AGENTS.md

## Project

Dude Fish OS is the new Flask-based operating system and public website for Dude Fish Printing, a family-run 3D printing business relocating to the Clarksville, Tennessee area.

This is a fresh rebuild. Do not preserve old architecture unless specifically asked. Build a clean, production-minded Flask app with a public website, private admin dashboard, mobile-friendly POS, full REST API, analytics, and containerized deployment.

## Business Context

Dude Fish Printing sells online, through Facebook, at vendor markets, through word of mouth, and eventually through local Clarksville-area business outreach.

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

A small Node/npm toolchain is allowed only for Tailwind. Do not make this a Node-first app.

Do not use React, Next.js, Vue, Angular, Prisma, Express, or a SPA architecture.


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

- Use a Flask application factory.
- Use blueprints.
- Keep routes thin.
- Put business logic in services.
- Put browser validation in forms.
- Put API validation/serialization in schemas.
- Use reusable Jinja components and partials.

## Security Rules

Never hardcode secrets.

Never commit `.env`.

Never commit real DB credentials, API keys, production secrets, or card data.

Use `.env.example` placeholders only. The real `.env` is local-only and must never be committed.

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
```

The repository may include a local starter `.env` only when the user explicitly requests it. If present, `.env` must be listed in `.gitignore` and treated as local machine configuration, not project documentation.

Implement:

- Password hashing
- Login/logout
- Role-based authorization
- CSRF protection
- API token auth for `/api/v1`
- Secure file uploads
- Safe filenames
- Upload size limits
- Friendly 403/404/500 pages
- Audit logs for important create/update/delete/admin actions

The POS must not process real cards in this version. Do not store card numbers, CVV, track data, or sensitive payment details. Card processing is a placeholder only. Cash payments are supported now. External card/Apple Pay/Venmo/Cash App can be recorded as external/manual methods only.

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

Add indexes for common filters/searches: slugs, SKUs, statuses, order numbers, customer email, market date, print job status, inventory location, and API token hashes.

## UX Rules

Build for real use by a small business owner.

The app must be responsive and clean.

The POS must be comfortable on a phone at a vendor market.

Admin tables should have search/filter where practical.

Forms need clear labels, validation, empty states, flash messages, cancel/back buttons, and confirmation for destructive actions.

Public site should feel warm, colorful, family-friendly, and polished.

Admin/POS should feel fast, practical, and clean.

Use Tailwind CSS throughout.

Use HTMX for inline updates when helpful, such as POS cart updates, print job status changes, and quick inventory adjustments.

## Required Modules

Build these modules:

1. Public website
2. Authentication and roles
3. Admin dashboard
4. Products
5. Categories
6. Collections
7. Product variants / SKUs
8. Design/model asset and license tracking
9. Printer fleet
10. AMS / multicolor unit tracking
11. Filament/material inventory
12. Finished goods inventory
13. Print job queue
14. Failed print tracking
15. Customers
16. Custom order requests
17. Orders, order items, payments
18. POS system
19. Vendor markets
20. Market packing lists
21. Market sales
22. Expenses
23. Analytics
24. API tokens
25. Full REST API
26. CSV import/export
27. Settings
28. Audit logs

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

Build:

- Home
- About
- Shop / Gallery
- Collection pages
- Product detail pages
- Custom Orders
- Small Business Products
- Military-Family-Safe Gifts
- Vendor Market Schedule
- FAQ
- Contact
- Privacy Policy placeholder
- Terms placeholder

## Admin Pages

Build CRUD/list/detail pages for:

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
- Print jobs
- Customers
- Orders
- Custom order requests
- Markets
- Market packing lists
- Market sales
- POS sessions
- Expenses
- Analytics
- API tokens
- Settings
- Users
- Audit logs

CRUD means list, detail, create, edit, archive/delete where appropriate, search/filter where practical, validation, flash messages, and API support where required.

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

Required API resources:

- products
- categories
- collections
- variants
- model-assets
- printers
- ams-units
- filament-spools
- inventory
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
- expenses
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
- How much cash should be in the drawer after a POS session?
- What payment methods were used at a market?
- What items sold through POS versus custom/online orders?

Use Chart.js for visual analytics.

## Seed Data

Create:

```bash
flask seed demo
```

Seed:

- Admin user
- Staff user
- Categories
- Collections
- Demo products
- Variants
- Printer fleet
- AMS units
- Filament spools
- Inventory locations
- Demo inventory
- Demo customers
- Demo custom orders
- Demo market
- Demo POS session
- Demo expenses

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
- Product model can be created
- Product admin list loads
- Product API requires token
- Product API returns data with token
- POS page requires auth
- POS can create a cash sale
- POS sale creates order/payment records
- Custom request public form validates
- CSV export returns a file response
- Analytics summary returns expected keys

## Build Behavior for Codex

When asked to build:

1. Read `AGENTS.md`
2. Read `PROMPTS.md`
3. Read `TODO.md`
4. Read `DESIGN.md`
5. Read `ARCHITECTURE.md`
6. Inspect repo files
7. Give a short implementation plan
8. Build one phase at a time
9. Run formatting/tests if possible
10. Update `TODO.md`
11. Summarize changed files
12. Explain how to run the app
13. Stop at requested phase

Do not build all phases in one giant pass unless explicitly requested.

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
- It has tests where practical
- It works in Docker
- It is documented
- It has no hardcoded secrets
