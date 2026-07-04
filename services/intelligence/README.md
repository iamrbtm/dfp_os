# DFP Intelligence

Decision intelligence microservice for Dude Fish OS. This service keeps historical imports, warehouse staging data, and product-alias cleanup outside the main Flask/MariaDB operational app.

## Current Scope

Implemented phases 1-10:

- FastAPI service scaffold with liveness/readiness checks.
- PostgreSQL 17 async SQLAlchemy models and Alembic migration.
- Internal bearer-token authentication for `/api/v1/*`.
- Square item CSV import into raw staging rows.
- Payment-sensitive Square fields are not stored in normal row payloads: `Token` and `PAN Suffix` are removed.
- Old MariaDB schema inspection design that records table/column snapshots without requiring live credentials in tests.
- Historical alias mapping records for product, variant, category, channel, customer, and market cleanup.
- Warehouse fact and summary rebuild from sanitized Square staging rows.
- Product, seasonal, and channel performance summaries.
- Deterministic Market Advisor recommendations with persisted runs, product quantities, print quantities, revenue estimates, risk level, and evidence.
- RAG-ready knowledge documents and chunks with lexical retrieval now and an embedding field reserved for future pgvector/vector search.
- Safe Ask DFP endpoint that uses allowlisted warehouse and knowledge-search tools only.
- Decision outcome records for tracking whether recommendations were accepted, planned, worked, or failed.
- Flask admin integration through the main DFPos app.

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
| `POST` | `/api/v1/imports/legacy-mariadb/import-all` | Import every table from legacy MariaDB into raw staging tables. |
| `GET` | `/api/v1/imports/legacy-mariadb/tables` | List imported tables with review state and row counts. |
| `GET` | `/api/v1/imports/legacy-mariadb/tables/{table_name}/review` | Get review state for a specific table. |
| `POST` | `/api/v1/imports/legacy-mariadb/tables/{table_name}/review` | Mark a table as keep/exclude/delete_staging. |
| `DELETE` | `/api/v1/imports/legacy-mariadb/tables/{table_name}/staging` | Hard-delete staging rows for a table (requires `confirm=true`). |

### Mappings

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/mappings` | List historical alias mappings. |
| `POST` | `/api/v1/mappings` | Create a proposed mapping. |
| `POST` | `/api/v1/mappings/{id}/review` | Mark a mapping reviewed and attach the DFPos target. |

### Warehouse

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/warehouse/rebuild-square` | Rebuild sales facts and product/seasonal/channel summaries from Square staging rows. |
| `GET` | `/api/v1/warehouse/products` | List product sales summaries ordered by units/revenue. |
| `GET` | `/api/v1/warehouse/channels` | List channel performance summaries. |
| `GET` | `/api/v1/warehouse/seasonal-products` | List product performance by month. |

### Advisor

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/advisor/market` | Generate a deterministic Market Advisor run from warehouse summaries and current inventory context. |

### Knowledge, Ask DFP, and Decision Log

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/knowledge/documents` | Store a note/document and create searchable chunks. |
| `GET` | `/api/v1/knowledge/search` | Search stored chunks with lexical retrieval. |
| `POST` | `/api/v1/ask` | Answer with allowlisted warehouse/search tools and evidence. |
| `POST` | `/api/v1/decision-outcomes` | Record feedback against a recommendation or run. |
| `GET` | `/api/v1/decision-outcomes` | List recent decision feedback. |

## Testing

```bash
uv run pytest
```

Tests use SQLite in memory and fixture CSV files, not live Square or MariaDB credentials.

## Next Work

- Add richer DFPos snapshot sync from current products, markets, inventory, expenses, print jobs, and receipts.
- Add pgvector-backed semantic retrieval once the Postgres extension is enabled in deployment.
- Add approved-action workflows that create prep tasks or print jobs in DFPos after human confirmation.
