# DFP OS API Docs

A standalone API documentation microservice for Dude Fish OS. Renders the OpenAPI 3.x spec from the main DFP OS application using [Redoc](https://redocly.com/redoc).

## How It Works

The docs service is **decoupled** from the main application:

1. The main DFP OS app generates an OpenAPI 3.0.3 spec automatically via **Flask-Smorest** (code-first approach).
2. The spec is exposed at `/api/openapi.json` on the main app (and also available via Swagger UI at `/api/docs` and Redoc at `/api/redoc`).
3. The docs microservice fetches the spec from the main app at startup (and periodically refreshes it).
4. Redoc renders the spec as a clean, searchable, interactive documentation site.
5. If the main app is unreachable, a local fallback spec file is used.

## Architecture

```
┌──────────────────────┐     HTTP fetch      ┌──────────────────────────┐
│   DFP OS Main App   │ ──────────────────▶  │  DFP OS API Docs         │
│   Flask + Smorest   │   /api/openapi.json  │  Flask + Redoc            │
│   Port 5000          │                      │  Port 8080                │
│                      │                      │                           │
│   Source of truth    │                      │  Renders spec with Redoc │
│   for all API routes │                      │  Health endpoint: /health │
│   schemas, auth      │                      │  Spec proxy: /openapi.json│
└──────────────────────┘                      └──────────────────────────┘
```

The main app remains the **source of truth**. All API routes, request schemas, response schemas, status codes, authentication requirements, and tags are defined in the main app's code. The docs service simply consumes and displays the generated spec.

## How It Gets the OpenAPI Spec

The service uses a **fetch with fallback** strategy:

1. **Primary**: Fetches from `DFPOS_OPENAPI_URL` (default: `http://localhost:5000/api/openapi.json`)
2. **Fallback**: If the remote is unreachable, reads from a local file at `DFPOS_OPENAPI_FALLBACK_PATH` (default: `./openapi/openapi.json`)
3. **Caching**: The spec is cached in memory and refreshed every `DFPOS_OPENAPI_REFRESH_INTERVAL` seconds (default: 300)

## Quick Start

### Prerequisites

- Python 3.14
- uv
- The main DFP OS app running (or a local `openapi.json` file)

### Setup

```bash
cd services/dfpos-api-docs

# Copy and configure environment
cp .env.example .env
# Edit .env if needed (defaults work for local development)

# Create virtual environment and install dependencies
uv sync

# Fetch the latest OpenAPI spec from the main app
uv run dfpos-docs-fetch

# Validate the spec
uv run dfpos-docs-validate
```

### Run Locally

```bash
# With the main app running on port 5000:
uv run python -m app.main
```

Open http://localhost:8080 in your browser.

### Run with Docker

```bash
# From the project root with the main app:
docker compose --profile docs up --build
```

The docs service will be available at http://localhost:8080.

## Scripts

All scripts are available as both shell scripts and `uv run` commands:

| Command | Shell Script | Description |
|---------|-------------|-------------|
| `uv run dfpos-docs-fetch` | `./scripts/fetch-spec.sh` | Fetch the latest OpenAPI spec from the main app and save it locally |
| `uv run dfpos-docs-validate` | `./scripts/validate-spec.sh` | Validate the local OpenAPI spec for correctness |
| `uv run dfpos-docs-build` | `./scripts/build.sh` | Fetch + validate (run before deployment) |

### CI Usage

```bash
# In CI, fetch and validate the spec in one step:
uv run dfpos-docs-build
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DFPOS_OPENAPI_URL` | `http://localhost:5000/api/openapi.json` | URL to fetch the OpenAPI spec from |
| `DFPOS_OPENAPI_FALLBACK_PATH` | `./openapi/openapi.json` | Local fallback spec file path |
| `DFPOS_OPENAPI_REFRESH_INTERVAL` | `300` | How often to refresh the spec (seconds, 0 = disabled) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8080` | Server port |
| `DOCS_USERNAME` | (empty) | Basic auth username (leave empty for no auth) |
| `DOCS_PASSWORD` | (empty) | Basic auth password |
| `SECRET_KEY` | `change-me-docs-secret` | Flask secret key |
| `APP_NAME` | `Dude Fish OS API Reference` | Title shown in the docs header |
| `REDOC_THEME` | `light` | Redoc theme: `light` or `dark` |
| `LOG_LEVEL` | `INFO` | Log level |

## Deployment

### Standalone

```bash
# Build and run with Docker
docker build -t dfpos-api-docs .
docker run -p 8080:8080 \
  -e DFPOS_OPENAPI_URL=https://your-app.com/api/openapi.json \
  dfpos-api-docs
```

### With Docker Compose

```bash
docker compose --profile docs up --build -d
```

### Behind a Reverse Proxy

Set `DOCS_USERNAME` and `DOCS_PASSWORD` for basic auth, or handle auth at the reverse proxy level. For private deployments, ensure `DFPOS_OPENAPI_URL` points to an internal endpoint that is not publicly exposed.

```nginx
# Example nginx configuration
server {
    listen 443 ssl;
    server_name docs.example.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Updating Docs When API Changes

When API functionality is added or changed:

1. The main app developer adds the endpoint using Flask-Smorest decorators (`@catalog_blp.route`, `@catalog_blp.arguments`, `@catalog_blp.response`).
2. Request/response schemas are defined using Marshmallow schemas in `app/schemas/`.
3. The OpenAPI spec at `/api/openapi.json` updates automatically (no manual spec writing).
4. The docs microservice picks up the new spec automatically (within the refresh interval).
5. For an immediate update, restart the docs service or trigger a fetch:
   ```bash
   uv run dfpos-docs-fetch
   ```

## API Map

The service exposes these internal endpoints:

| Endpoint | Description |
|----------|-------------|
| `/` | Redoc documentation site |
| `/health` | Health check (returns spec status) |
| `/openapi.json` | Cached/proxied OpenAPI spec |
| `/api/v1/openapi.json` | Alias for `/openapi.json` |

## Testing

```bash
uv run pytest
```

Tests cover:
- Health endpoint with and without a spec loaded
- Index page rendering with and without a spec
- OpenAPI JSON proxy endpoint
- 404 error handling
- Spec validation logic

## Security Notes

- The docs service does **not** require database access.
- It does **not** import the main app runtime.
- Sensitive example values in the OpenAPI spec should be redacted at the source (main app schemas should use placeholder/default values rather than real secrets).
- Basic auth can be enabled by setting `DOCS_USERNAME` and `DOCS_PASSWORD`.
- The docs service only exposes endpoints that are documented in the OpenAPI spec; it does not expose internal endpoints unless explicitly configured.
