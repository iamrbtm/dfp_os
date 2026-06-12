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

## Database and Admin Seed

```bash
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

## Docker

```bash
docker compose up --build
```

The web app runs at `http://localhost:5000`, backed by MariaDB in the `db` service on port `3306`.

The container keeps its own virtualenv and `node_modules` in Docker volumes so it does not conflict with a local macOS or Linux `.venv`.
On startup, the web container also builds `app/static/dist/app.css` so Tailwind styles are present in development.
If you want to use the optional local MariaDB container instead of an external database, start it with `docker compose --profile localdb up --build`.
