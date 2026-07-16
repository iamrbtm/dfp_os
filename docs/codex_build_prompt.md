# Codex Build Prompt for Dude Fish OS

You are working in a fresh GitHub repository for Dude Fish OS.

This is a clean rebuild. Ignore old architecture from prior experiments. Build the application from scratch with Flask, Jinja templates, Tailwind CSS, MariaDB, SQLAlchemy, Flask-Migrate, Docker, and a full REST API.

Before coding, read:

- `AGENTS.md`
- `DESIGN.md`

Then inspect the repository. If files already exist, identify what can stay and what should be replaced. Preserve `.git`, `AGENTS.md`, `DESIGN.md`, `.gitignore`, `.env.example`, and README unless there is a clear reason to update them. Do not commit secrets.

## Product Goal

Build a complete, polished, production-minded small-business operating system for Dude Fish Printing.

The app must include:

1. Public website
2. Admin dashboard
3. Product catalog
4. Product CRUD
5. Category/collection/variant CRUD
6. Design/model license tracking
7. Printer fleet management
8. AMS/multicolor unit tracking
9. Filament/material inventory
10. Finished goods inventory
11. Print job queue
12. Customer management
13. Custom order requests
14. Orders/order items/payments
15. Vendor market planning
16. Market packing lists
17. Expenses
18. Analytics
19. Mobile-friendly POS system
20. Full REST API
21. API token management
22. CSV import/export
23. Dockerized local development
24. Tests and documentation

## Required Stack

Use:

- Python 3.14
- uv for Python version management, dependency locking, and command execution
- Flask
- Jinja2
- MariaDB
- SQLAlchemy
- Flask-Migrate / Alembic
- Flask-Login
- Flask-WTF
- Tailwind CSS
- Vanilla JavaScript
- HTMX where useful
- Alpine.js only where useful
- Chart.js
- Flask-Smorest or Flask-RESTX for API/OpenAPI
- Marshmallow or Pydantic for schemas
- Docker
- Docker Compose
- Gunicorn
- Pytest
- Ruff/Black

Do not use Next.js, Vue, Angular, Prisma, Express, or a Node-first backend. Node/npm is allowed for Tailwind asset building.

The public website and admin dashboard must be Flask/Jinja-first. The POS may use a small Preact + TypeScript + Vite frontend island only if that gives a cleaner, faster high-volume checkout screen. If Preact is used, it must be limited to `/pos`; Flask still owns auth, APIs, persistence, order creation, payment recording, and inventory deduction.


## uv and Python 3.14 Requirements

Use Python 3.14 and uv.

Create and maintain:

```text
.python-version
pyproject.toml
uv.lock
```

`.python-version` must contain:

```text
3.14
```

Use these command patterns in documentation and scripts:

```bash
uv python install 3.14
uv python pin 3.14
uv sync
uv run flask --app app:create_app db upgrade
uv run flask --app app:create_app seed demo
uv run flask --app app:create_app run
uv run pytest
uv run ruff check .
```

Do not create `requirements.txt` as the primary dependency file. Use `pyproject.toml` and `uv.lock` as the source of truth.

Before completing Phase 1, run or document running:

```bash
uv lock
uv run pytest
```

If any dependency fails to resolve or run under Python 3.14, choose a compatible replacement and explain the change.

## Required Structure

Create this structure:

```text
app/
  __init__.py
  config.py
  extensions.py
  cli.py
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
    expenses/
    analytics/
    pos/
    api/
    settings/
  forms/
  schemas/
  services/
  templates/
    base.html
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
    expenses/
    analytics/
    pos/
    settings/
    components/
    errors/
  static/
    src/
      input.css
      js/
    dist/
  utils/
migrations/
tests/
scripts/
docs/
uploads/
  .gitkeep
.env.example
.gitignore
Dockerfile
docker-compose.yml
pyproject.toml
package.json
tailwind.config.js
postcss.config.js
README.md
```

Use the Flask application factory pattern. Use blueprints. Keep routes thin. Put business logic in services.

## Environment Variables

Create `.env.example` with placeholders only:

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

Do not use real credentials.

## POS System Requirements

Build POS as a core module.

Route:

```text
/pos
```

It must work on mobile, tablet, and desktop.

POS features:

- Open/close POS session
- Choose active market/event
- Choose inventory location
- Product tile buttons like Square
- Category tabs
- Product search
- Tap/click item to add to cart
- Quantity controls
- Remove item
- Add custom item with manual description and price
- Add custom order deposit
- Quick customer creation
- Optional customer link
- Cash payment
- External card placeholder
- Venmo/Cash App/Apple Pay/Other payment recording
- Change due calculation for cash
- Receipt/confirmation page
- Inventory deduction
- Create order/payment records
- Attribute sale to market/POS session
- End-of-day cash/payment summary

Card processing placeholder rules:

- Do not implement real card processing yet
- Do not store card numbers, CVV, track data, or sensitive payment information
- External Card Placeholder may record only amount, status, and optional external reference
- Leave service boundaries for future Square or Stripe integration

Custom orders from POS:

- POS must have a Custom Order action
- It should allow creating a custom request from POS
- It should allow collecting a deposit
- It should link the deposit to an order/payment/custom request

## Public Website Pages

Build these pages:

- Home
- About
- Shop/Gallery
- Product collection pages
- Product detail pages
- Custom Orders
- Small Business Products
- Military-Family-Safe Gifts
- Vendor Market Schedule
- FAQ
- Contact
- Privacy Policy placeholder
- Terms placeholder

The public site should look polished, friendly, colorful, and family-run.

## Admin Pages

Build admin/dashboard pages for:

- Dashboard
- Products
- Categories
- Collections
- Variants
- Model assets/licenses
- Printers
- AMS units
- Filament
- Inventory locations
- Inventory
- Print jobs
- Customers
- Orders
- Custom orders
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

For each major resource, enforce CRUD where needed:

- List
- Detail
- Create
- Edit
- Archive/delete
- Search/filter
- Flash messages
- Validation
- API support

## Full API

Build REST API under:

```text
/api/v1/
```

API must include:

- Token authentication
- JSON responses
- Pagination
- Filtering where practical
- Sorting where practical
- Search where practical
- OpenAPI docs
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

## Build Phases

Do not build all phases in one giant pass. Work phase by phase.

### Phase 1: Foundation

Build:

- Flask app factory
- Config
- Extensions
- MariaDB connection
- Flask-Migrate
- Flask-Login
- CSRF
- Base Jinja layout
- Tailwind setup
- Dockerfile
- docker-compose.yml
- `.env.example`
- README
- Public home page
- Login/logout
- User model
- Role field
- Dashboard shell
- CLI seed admin command
- Pytest smoke tests

After Phase 1, stop and summarize:

- Files created/changed
- Commands to run
- Tests run
- What Phase 2 should do

### Phase 2: Catalog and Fleet

Build:

- Products
- Categories
- Collections
- Variants
- Model assets/license tracking
- Printers
- AMS units
- Filament spools
- Inventory locations
- Basic finished goods inventory
- Admin CRUD pages
- API endpoints
- Seed demo data

### Phase 3: Orders, Custom Requests, Print Jobs

Build:

- Customers
- Public custom order form
- Custom order admin workflow
- Orders
- Order items
- Payments
- Print jobs
- Print job queue
- Inventory adjustments
- Convert custom request to order
- Create print job from order item
- API endpoints

### Phase 4: POS

Build:

- POS session open/close
- POS screen
- Product tile buttons
- Cart
- Cash checkout
- External card placeholder
- Other payment methods
- Custom item
- Custom order deposit
- Customer quick create
- Receipt page
- Inventory deduction
- POS sale/order/payment records
- Market attribution
- End-of-day summary
- POS API
- POS tests

### Phase 5: Markets and Expenses

Build:

- Vendor markets
- Market packing lists
- Market sales
- Market performance review
- Expenses
- CSV exports
- API endpoints
- Admin pages

### Phase 6: Analytics and Polish

Build:

- Executive analytics
- Product analytics
- Market analytics
- POS analytics
- Printing analytics
- Inventory analytics
- Expense analytics
- Chart.js visualizations
- Public site polish
- SEO basics
- Error pages
- API docs polish
- Tests
- Deployment docs

## Start Now

Start by implementing Phase 1 only.

Before coding, produce a concise plan for Phase 1.

Then implement Phase 1.

Run tests or explain why they cannot be run.

Stop after Phase 1 and provide a summary.

Do not continue into Phase 2 until asked.

## Quality Bar

This must look and feel ready for real use. Do not build ugly placeholder screens unless absolutely necessary. Use Tailwind to make it clean and polished from the start.

A feature is not done unless it has:

- Database model if persistent
- Migration if schema changes
- Form/schema validation
- Admin UI where needed
- API endpoint where required
- Error handling
- Flash messages or user feedback
- Tests where practical
- Documentation updates
- No hardcoded secrets
