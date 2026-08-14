# Trend Scout Microservice

The Trend Scout microservice extracts the AI Design Trend Scout from the Dude Fish OS
Flask monolith into a standalone FastAPI service. It runs the same weekly pipeline
(fetch → analyze → score → synthesize) with independent resource scaling, isolated
failure boundaries, and its own database and Redis.

This is phase 1 of the initiative tracked in `docs/trend_scout_microservice_plan.md`.

## Status (Phase 1 — scaffold)

| Component | Status |
|---|---|
| FastAPI app + health endpoints | done |
| Async SQLAlchemy + asyncpg engine | done |
| Bearer token security + scope helpers | done |
| Celery instance with low-priority `trend_scout` queue | done |
| Alembic async migrations | done |
| Initial migration (5 tables) | done |
| Dockerfile + healthcheck | done |
| docker-compose wiring | pending (Phase 6 cutover) |
| Source migration | pending (Phase 2) |
| Analyzer + scoring | pending (Phase 3) |
| Pipeline tasks | pending (Phase 4) |
| Full API surface | pending (Phase 5) |
| Firecrawl integration | pending (Phases 7-9) |

## Running locally

```bash
cd services/trend-scout
cp .env.example .env
# Edit .env: set TREND_SCOUT_INTERNAL_API_TOKEN, TREND_SCOUT_DATABASE_URL, etc.

uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8093
```

The service exposes:

- `GET /health/live` — always-200 liveness
- `GET /health/ready` — DB + Redis + Celery status
- `GET /health/deep` — deep dependency check
- `GET /health/ping` — trivial 200 for load balancers
- `GET /api/v1/openapi.json` — OpenAPI spec (no Swagger UI in this phase)

## Migrations

```bash
cd services/trend-scout
uv run alembic upgrade head
```

## Tests

```bash
cd services/trend-scout
uv run pytest -v
```

## Environment

All env vars are prefixed with `TREND_SCOUT_`. See `.env.example` for the full list.

Key vars:

- `TREND_SCOUT_DATABASE_URL` — async Postgres URL
- `TREND_SCOUT_REDIS_URL` — Redis DB 2 (trend-scout streams)
- `TREND_SCOUT_CELERY_BROKER_URL` / `TREND_SCOUT_CELERY_RESULT_BACKEND` — Redis DB 1 (Celery)
- `TREND_SCOUT_INTERNAL_API_TOKEN` — Bearer token for the Flask app
- `TREND_SCOUT_AUDIT_LOG_*` — Audit log forwarding config

## Architecture

```
HTTP (Flask proxy, Phase 6) ──► FastAPI app ──► Postgres (own logical DB)
                                  │
                                  ├─► Redis (streams, queues, cache)
                                  │
                                  └─► Celery (low-priority queue)
                                       │
                                       └─► workers/stream_worker (Phase 4)
```

## See also

- `docs/trend_scout_microservice_plan.md` — full initiative plan
- `docs/trend_scout_setup.md` — operator setup guide (rewritten at Phase 10)
- `services/intelligence/` — sister microservice used as the structural template
- `services/audit-log/` — audit dispatch target
