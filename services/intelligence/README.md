# DFP Intelligence

Decision intelligence microservice for Dude Fish OS. This service keeps historical imports, warehouse staging data, and product-alias cleanup outside the main Flask/MariaDB operational app.

## Current Scope

Implemented phases 1-4:

- FastAPI service scaffold with liveness/readiness checks.
- PostgreSQL 17 async SQLAlchemy models and Alembic migration.
- Internal bearer-token authentication for `/api/v1/*`.
- Square item CSV import into raw staging rows.
- Payment-sensitive Square fields are not stored in normal row payloads: `Token` and `PAN Suffix` are removed.
- Old MariaDB schema inspection design that records table/column snapshots without requiring live credentials in tests.
- Historical alias mapping records for product, variant, category, channel, customer, and market cleanup.

The main DFPos Flask app remains the operational source of truth. This service should recommend and explain decisions, not directly mutate DFPos business records.

## Quick Start

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8091
```

Health checks:

```bash
curl http://localhost:8091/health/live
curl http://localhost:8091/health/ready
```

## Docker

From the repo root:

```bash
docker compose up intelligence-postgres intelligence --build
```

The service listens on `http://localhost:8091`.

## API

All `/api/v1/*` endpoints require:

```text
Authorization: Bearer <INTELLIGENCE_INTERNAL_API_TOKEN>
```

### Imports

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/imports/square/items-csv` | Import Square itemized sales CSV into raw staging rows. |
| `POST` | `/api/v1/imports/legacy-mariadb/inspect` | Inspect legacy MariaDB table/column shape and save a schema snapshot. |

### Mappings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/mappings` | List historical alias mappings. |
| `POST` | `/api/v1/mappings` | Create a proposed mapping. |
| `POST` | `/api/v1/mappings/{id}/review` | Mark a mapping reviewed and attach the DFPos target. |

## Testing

```bash
uv run pytest
```

Tests use SQLite in memory and fixture CSV files, not live Square or MariaDB credentials.

## Next Phases

- Phase 5: warehouse fact/dimension tables and materialized summaries.
- Phase 6: deterministic Market Advisor recommendations.
- Phase 7: RAG support for notes, receipts, and product descriptions.
- Phase 8: safe Ask DFP endpoints with allowlisted tools.
- Phase 9: Flask admin integration.
- Phase 10: decision log and outcome feedback loop.
