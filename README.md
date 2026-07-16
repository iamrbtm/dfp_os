# Dude Fish OS

Dude Fish OS is the new Flask-based public website and internal operating system for Dude Fish Printing. Phase 1 establishes the production-minded foundation: app factory, auth, dashboard shell, database wiring, CLI seeding, Docker, and smoke tests.

## Phase 1 Includes

- Flask application factory at `app:create_app`
- Environment-aware config for development, testing, and production
- SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, Flask-Smorest, and MariaDB-ready setup
- Public home page
- Login/logout flow with hashed passwords and role-aware `User` model
- Login-protected dashboard shell
- Seed CLI for the initial admin account
- Docker and Docker Compose baseline
- Pytest smoke coverage

## Prerequisites

- Python `3.14`
- `uv`
- Node.js and npm for Tailwind asset builds
- Docker Desktop or compatible Docker engine for containerized development

## Setup

```bash
uv python install 3.14
uv python pin 3.14
uv sync
npm install
npm run build:css
```

## Environment

Copy `.env.example` to `.env` for local development and fill in safe local values only.

Required environment variables:

- `SECRET_KEY`
- `DATABASE_URL`
- `APP_NAME`
- `APP_BASE_URL`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `UPLOAD_FOLDER`
- `MAX_CONTENT_LENGTH_MB`
- `POS_CARD_PROCESSING_ENABLED`
- `POS_CARD_PROCESSOR`

The application reads `DATABASE_URL` from your local `.env`. Docker does the same, so there is a single source of truth for the active database connection.

Important database routing:

- From inside the Docker network, the MariaDB hostname is `db`.
- From your host machine, use `127.0.0.1:3306`.
- The main app database is `dudefish_os`.
- The test suite should use `TEST_DATABASE_URL` and the separate `dudefish_os_test` database.

## Database and Admin Seed

```bash
docker compose up -d db
uv run flask --app app:create_app db upgrade
uv run flask --app app:create_app seed admin
```

## Run the App

```bash
uv run flask --app app:create_app run --debug
```

Open `http://localhost:5000`.

## Tailwind Development

```bash
npm run watch:css
```

## Tests and Checks

```bash
uv run pytest
uv run ruff check .
uv run black --check .
```

Host-side test and migration defaults are expected to point at the Docker MariaDB service:

```env
DATABASE_URL=mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os
TEST_DATABASE_URL=mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os_test
```

## Production Foundation Notes

This branch includes the modular-monolith foundation:

- `app/module_registry.py` declares module keys, feature flags, dependencies, nav/API resources, permissions, health checks, and docs locations.
- Feature flags can be stored as `FeatureFlag` records or `Setting` keys such as `module.pos.enabled`; disabled modules are blocked server-side for routes and `/api/v1` resources.
- `Business` provides a single default Dude Fish Printing account now, with nullable `business_id` fields on major business records for SaaS-later readiness.
- POS product sales deduct inventory from the active POS session location and record `InventoryMovement` rows.
- Receipts require manual approval before creating expense ledger entries; AI receipt parsing and analytics insights are disabled unless explicitly enabled.
- Cost Engine and Prep Tasks are service modules with token-protected API endpoints.

Local `.env` files are ignored by git. Be careful with `docker compose config`: Docker expands local environment values into its rendered output, so do not paste that output publicly if your local `.env` contains real secrets. Rotate any secret that has been exposed.

## Docker

```bash
docker compose --env-file .env.example --profile release run --rm migrate
docker compose --env-file .env.example up --build web worker beat audit-log intelligence
```

The web app runs at `http://localhost:5000`. Internal databases, Redis, audit-log, intelligence, and object storage are exposed only inside the Docker network by default.

Migrations are intentionally not run by the web container. Run the `release` profile `migrate` service before deploying a new image.

The production image builds Python dependencies with `uv sync --frozen --no-dev`, builds Tailwind during image build, and runs as a non-root user. For local development, use `.env.example` as a template and replace every `change-me` value before using compose on any reachable host.

### E2E Tests

Playwright smoke tests live under `tests/e2e/`.

```bash
npm install
npx playwright install
E2E_BASE_URL=http://127.0.0.1:5000 npm run test:e2e
```

Seed demo/admin data before running E2E tests so `/pos` has an openable session and product tiles.

## API Documentation

DFP OS uses a **code-first OpenAPI** approach. The API documentation is generated automatically from the code and does not need to be hand-written.

### How It Works

1. API routes are defined using **Flask-Smorest** decorators in `app/blueprints/api/routes.py`.
2. Request and response schemas are defined as **Marshmallow** classes in `app/schemas/`.
3. Flask-Smorest generates an OpenAPI 3.0.3 spec automatically from the decorators and schemas.
4. The spec is available at `/api/openapi.json`.
5. Interactive documentation is available at:
   - **Swagger UI**: `/api/docs` — for interactive endpoint testing
   - **Redoc**: `/api/redoc` — for clean, searchable reference docs

### Viewing Docs

- **Development**: Navigate to `http://localhost:5000/api/docs` (Swagger UI) or `http://localhost:5000/api/redoc` (Redoc).
- **Production**: A separate [API Docs microservice](services/dfpos-api-docs/) can be deployed alongside the main app for better isolation.

### Documenting a New API Route

When adding a new API endpoint, follow these steps:

1. **Define the schema** in `app/schemas/` (if it doesn't already exist):
   ```python
   from marshmallow import Schema, fields

   class WidgetSchema(Schema):
       id = fields.Integer(dump_only=True)
       name = fields.String(required=True)
       color = fields.String()
       created_at = fields.DateTime(dump_only=True)
   ```
   - Use `required=True` for fields that must be present in requests.
   - Use `dump_only=True` for server-generated fields (id, timestamps).
   - Use `allow_none=True` for optional fields.

2. **Add the route** in `app/blueprints/api/routes.py` using Flask-Smorest decorators:
   ```python
   @catalog_blp.route("/widgets")
   @catalog_blp.doc(tags=["Widgets"])
   class WidgetCollection(MethodView):
       @api_token_required
       @catalog_blp.response(200, WidgetSchema(many=True))
       def get(self):
           widgets = Widget.query.all()
           return WidgetSchema(many=True).dump(widgets)

       @api_token_required
       @catalog_blp.arguments(WidgetSchema)
       @catalog_blp.response(201, WidgetSchema)
       def post(self, body_data):
           widget = Widget(**body_data)
           db.session.add(widget)
           db.session.commit()
           return WidgetSchema().dump(widget), 201

   @catalog_blp.route("/widgets/<int:widget_id>")
   @catalog_blp.doc(tags=["Widgets"])
   class WidgetItem(MethodView):
       @api_token_required
       @catalog_blp.response(200, WidgetSchema)
       def get(self, widget_id):
           widget = db.session.get(Widget, widget_id)
           if widget is None:
               return {"error": {"code": "not_found", "message": "Widget not found."}}, 404
           return WidgetSchema().dump(widget)
   ```

3. **Register import** in `app/schemas/__init__.py` (and add the model import in `routes.py`).

4. The OpenAPI spec updates **automatically**. No manual spec editing needed.

### Decorator Reference

| Decorator | Purpose | Required? |
|-----------|---------|-----------|
| `@catalog_blp.route("/path")` | Defines the URL route | Yes |
| `@catalog_blp.doc(tags=[...])` | Adds tags for grouping in docs | Recommended |
| `@catalog_blp.arguments(Schema)` | Documents and validates request body | Required for POST/PUT |
| `@catalog_blp.response(200, Schema)` | Documents response schema | Recommended |
| `@api_token_required` | Requires API token auth | Required for all API endpoints |

### Response Format

All list endpoints return a paginated envelope:
```json
{
    "data": [...],
    "pagination": {
        "page": 1,
        "per_page": 25,
        "total": 100,
        "pages": 4
    }
}
```

Error responses follow a consistent format:
```json
{
    "error": {
        "code": "not_found",
        "message": "Resource not found.",
        "details": {}
    }
}
```

HTTP status codes:
- `200` — Success
- `201` — Created
- `400` — Validation error
- `401` — Unauthorized (missing/invalid API token)
- `404` — Not found
- `422` — Schema validation error

### API Docs Microservice

A dedicated [API Docs microservice](services/dfpos-api-docs/) can be deployed alongside the main app:

```bash
# Start the main app and docs service
docker compose --profile docs up --build

# The docs site is available at http://localhost:8080
```

The docs microservice fetches the OpenAPI spec from `/api/openapi.json` on the main app and renders it using Redoc. It runs independently and does not require database access.

See the [microservice README](services/dfpos-api-docs/README.md) for full documentation.

### Validating the OpenAPI Spec

```bash
# From the docs microservice directory
cd services/dfpos-api-docs
uv run dfpos-docs-validate
```

This checks that the spec is valid OpenAPI 3.x, has an info block, has paths with responses, and has no obvious structural issues. CI pipelines should run this check after any API changes.

## GitHub Integration

This repo uses GitHub Issues and Projects for tracking work.

### Issues

Use the issue templates to file bug reports, feature requests, and tasks. Each issue should be labeled with the appropriate type, module, and priority.

### Labels

Labels are organized into categories (type, module, priority, status). Sync labels to the repo with:

```bash
./scripts/sync-labels.sh
```

### Project Board

A Kanban-style project board is configured with automated column transitions:
- **Backlog** → new issues autolink here
- **To Do** → issues targeted for the current milestone
- **In Progress** → actively being worked on
- **Review** → PR open, linked issue moves automatically
- **Done** → PR merged, linked issue closes automatically

### CI

The CI workflow (`.github/workflows/ci.yml`) runs on every push/PR to `main`:
1. **Lint job:** Ruff checks + format validation
2. **Test job:** MariaDB service container, migration, seed, pytest

See [docs/contributing.md](docs/contributing.md) for the full contribution workflow.
