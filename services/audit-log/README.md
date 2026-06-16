# DFP Audit Log

Append-only audit log microservice for Dude Fish OS. Provides tamper-evident event recording with HMAC-SHA256 hash chaining.

## Stack

- **FastAPI** — async web framework
- **PostgreSQL 17** — primary data store
- **SQLAlchemy 2.x** — async ORM
- **Alembic** — schema migrations
- **Redis 7** — stream-based event ingestion (optional)
- **Pydantic v2** — request/response validation
- **OpenTelemetry** — observability hooks

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  DFP OS     │────▶│ Audit Log   │────▶│ PostgreSQL   │
│  (Flask)    │     │ (FastAPI)   │     │ (events)     │
└─────────────┘     └──────┬──────┘     └──────────────┘
                           │ optional
                           ▼
                     ┌──────────┐
                     │  Redis   │
                     │ Stream   │
                     └──────────┘
```

## Quick Start

```bash
# Copy and edit environment
cp .env.example .env

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Start the service
uv run uvicorn app.main:app --reload --port 8090
```

The API is available at `http://localhost:8090`.

## API

All endpoints under `/api/v1/` require the `Authorization: Bearer <token>` header.

### Events

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/audit-events` | Create one audit event |
| `POST` | `/api/v1/audit-events/batch` | Batch create (max 100) |
| `GET` | `/api/v1/audit-events` | Search events (paginated) |
| `GET` | `/api/v1/audit-events/{id}` | Get event by ID |
| `GET` | `/api/v1/entities/{type}/{id}/timeline` | Entity timeline |
| `GET` | `/api/v1/actors/{id}/timeline` | Actor timeline |
| `POST` | `/api/v1/audit-events/verify-chain` | Verify hash chain integrity |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (checks DB) |

## Hash Chaining

Each event stores an HMAC-SHA256 hash computed from all event fields plus the previous event's hash. The chain can be verified at any time by recomputing hashes and checking links.

```
event_1: hash = HMAC(id || occurred_at || ... || previous_hash=None)
event_2: hash = HMAC(id || occurred_at || ... || previous_hash=event_1.hash)
event_3: hash = HMAC(id || occurred_at || ... || previous_hash=event_2.hash)
```

Tampering with any field in any event breaks the chain, which is detected by the `verify-chain` endpoint.

Payload for `_stable_json` sorts keys and uses compact separators for deterministic serialization.

## Configuration

All settings via environment variables with `AUDIT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIT_DATABASE_URL` | `postgresql+asyncpg://...` | Async DB connection |
| `AUDIT_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `AUDIT_INTERNAL_API_TOKEN` | `change-me-local-token` | Bearer token for API auth |
| `AUDIT_HASH_SECRET` | `change-me-local-hash-secret` | HMAC signing key |
| `AUDIT_USE_REDIS_STREAM` | `false` | Enable Redis stream ingestion |
| `AUDIT_LOG_LEVEL` | `INFO` | Python log level |

## Redis Stream Mode

Set `AUDIT_USE_REDIS_STREAM=true` to publish events to a Redis stream instead of writing directly to PostgreSQL. A background worker reads from the stream and persists events.

```bash
# Run the worker
uv run python -m app.workers.stream_consumer
```

## Docker

```bash
# Start everything
docker compose --profile audit up --build
```

The audit-log service runs on port `8090`. PostgreSQL on `5432`, Redis on `6379`.

## Testing

```bash
uv run pytest        # all tests (uses SQLite in-memory)
uv run pytest -v     # verbose
uv run pytest -x     # stop on first failure
```

## Schema

Migrations live in `alembic/versions/`. Create a new migration:

```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```
