# Trend Scout — Setup Guide

## Overview

The Trend Scout is an autonomous trend monitoring system that collects data from 10 sources (3D printing marketplaces, social platforms, and internal demand signals) and produces weekly opportunity reports with scored product recommendations.

## Environment Variables

Add these to your `.env` file:

```env
# OpenAI — used for AI-powered report summaries (optional, deterministic fallback exists)
OPENAI_API_KEY=sk-...
OPENAI_MODEL_TREND_SCOUT=gpt-4o-mini

# Etsy — product/trend data
ETSY_API_KEY=your-etsy-api-key

# Pinterest — visual trend discovery
PINTEREST_API_KEY=your-pinterest-api-key

# Google Trends — search interest data (via SerpAPI)
SERPAPI_API_KEY=your-serpapi-key

# TikTok — video trend data (requires approved Research API access)
TIKTOK_RESEARCH_ACCESS_TOKEN=your-tiktok-research-token

# Celery — required for pipeline execution
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### Source Configuration Status

| Source | Requires Env Var | Works Without? | Notes |
|---|---|---|---|
| `internal_demand` | None | Yes | Internal DB queries |
| `makerworld` | None | Yes | Uses `curl_cffi` |
| `printables` | None | Yes | Web scraping + RSS |
| `myminifactory` | None | Yes | Public search API |
| `reddit` | None | Yes | RSS feeds via curl |
| `bgg` | None | Yes | BoardGameGeek XML API |
| `etsy` | `ETSY_API_KEY` | No | Returns error result |
| `pinterest` | `PINTEREST_API_KEY` | No | Returns error result |
| `google_trends` | `SERPAPI_API_KEY` | Partial | Falls back to `pytrends` (no key needed) |
| `tiktok` | `TIKTOK_RESEARCH_ACCESS_TOKEN` | No | Returns error result |

The Source Health dashboard (under Latest Report) shows a green checkmark for configured sources and a yellow warning for unconfigured ones.

## API Key Setup

### Etsy
1. Register at https://developers.etsy.com/
2. Create a new app to get an API key
3. Set `ETSY_API_KEY` in `.env`

### Pinterest
1. Go to https://developers.pinterest.com/
2. Create a new app and generate an access token
3. Set `PINTEREST_API_KEY` in `.env`

### Google Trends (SerpAPI)
1. Sign up at https://serpapi.com/ (free tier available)
2. Get your API key from the dashboard
3. Set `SERPAPI_API_KEY` in `.env`
4. Without SerpAPI, falls back to `pytrends` (no key needed, but rate-limited)

### TikTok Research API
1. Apply at https://developers.tiktok.com/products/research-api/
2. Requires approved research application
3. Set `TIKTOK_RESEARCH_ACCESS_TOKEN` in `.env`

### OpenAI (for report summaries)
1. Get an API key from https://platform.openai.com/api-keys
2. Set `OPENAI_API_KEY` in `.env`
3. The pipeline works without this — a deterministic summary is generated instead

### MakerWorld
No API key needed. Requires `curl_cffi`:
```bash
uv add curl_cffi
```

## Database Migrations

The Trend Scout uses two Alembic migrations. Run:

```bash
uv run flask --app app:create_app db upgrade
```

This applies:

1. `787cadb6f437_add_trend_scout_tables.py` — Creates `trend_reports` and `trend_snapshots` tables
2. `a7b8c9d0e1f2_add_trend_opportunity_scores_and_source_health.py` — Creates `trend_opportunity_scores` and `source_health_records` tables

Verify migration status:
```bash
uv run flask --app app:create_app db current
```

All tables use MariaDB. Expected table count from Trend Scout: 4 tables.

## Running the Pipeline

### Via Admin UI
1. Log in as an admin user
2. Navigate to **Admin → AI Trend Scout** (`/admin/trend-scout`)
3. Click **Run Pipeline**
4. A progress bar shows real-time status via HTMX polling
5. On completion, the report appears with the opportunity matrix

### Via Celery (scheduled)
The pipeline runs automatically every **Monday at 6:00 AM** via Celery Beat. To start:

```bash
# Terminal 1: Celery worker
docker compose up celery-worker -d
# or locally:
uv run celery -A app.celery_app.celery worker --loglevel=info

# Terminal 2: Celery beat scheduler
docker compose up beat -d
# or locally:
uv run celery -A app.celery_app.celery beat --loglevel=info
```

### Via Flask CLI
```bash
uv run flask --app app:create_app trend-scout run
```

### Via direct Python
```bash
uv run python -c "
from app.services.ai.trend_scout import run_full_pipeline
result = run_full_pipeline()
print(f'Success: {result.get(\"success\")}')
print(f'Snapshots: {result.get(\"total_snapshots\")}')
print(f'Report: {result.get(\"report_id\")}')
"
```

## Pipeline Architecture

```
Run Pipeline (UI/CLI/Celery)
  └─ run_full_pipeline()
       ├─ Fetcher 1 (internal_demand) — DB query, sequential
       ├─ Fetcher 2..10 — run in ThreadPoolExecutor (max 4 workers)
       │    ├─ makerworld (curl_cffi scrape)
       │    ├─ printables (web scrape + RSS)
       │    ├─ myminifactory (API)
       │    ├─ etsy (API, needs key)
       │    ├─ google_trends (SerpAPI or pytrends)
       │    ├─ tiktok (API, needs key)
       │    ├─ reddit (RSS via curl)
       │    ├─ pinterest (API, needs key)
       │    └─ bgg (XML API)
       ├─ Snapshot persistence (TrendSnapshot rows)
       ├─ run_analysis()
       │    ├─ Velocity/momentum computation
       │    ├─ Category discovery (NLP embeddings + DBSCAN)
       │    ├─ Opportunity scoring (7 dimensions)
       │    ├─ TrendReport creation
       │    ├─ TrendOpportunityScore persistence
       │    └─ SourceHealthRecord persistence
       └─ Result dict with summary, report_id, error list
```

## Verifying Pipeline Health

### Admin Dashboard
Navigate to `/admin/trend-scout` and check the **Source Health** table:

| Column | What It Shows |
|---|---|
| Source | Data source name |
| Status | OK (green) or Error (red) |
| Items | Count of items fetched |
| Provider | Configured (green check) or Not configured (yellow warning) |
| Age | Time since last scrape (e.g. "2h ago", "3d ago") |
| Freshness | Score 0–100 based on data age |
| Details | Error message or keyword searched |

### API Endpoint
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:5000/api/v1/trend-scout/source-health
```

### Backtest / Calibration
Navigate to `/admin/trend-scout/backtest` to compare past scores against actual sales data.

## Scoring Weights

Scoring weights are stored in the `Setting` table with these key prefixes:

| Prefix | Purpose | Default Keys |
|---|---|---|
| `trend_weight.` | Score dimension weights (7 keys) | `purchase_intent`, `trend_velocity`, etc. |
| `trend_source.` | Source signal weights (10 keys) | `internal_demand`, `etsy`, `makerworld`, etc. |
| `trend_buyer.` | Buyer intent source weights (6 keys) | `internal_demand`, `etsy`, `google_trends`, etc. |
| `trend_metric.` | Item metric weights (20 keys) | `downloads`, `likes`, `num_favorers`, etc. |

Edit via **Admin → Settings** under the "Trend Scout" section.

Seed default weights:
```bash
uv run flask --app app:create_app seed demo
```

## Development

### Tests
```bash
# All trend scout tests
uv run pytest tests/test_trend_scout.py -v

# Unit tests only (no DB needed)
uv run pytest tests/test_trend_scout.py -v -k "not db"

# Weight + backtest tests
uv run pytest tests/test_trend_scout.py -v -k "weight or backtest"
```

### Adding a New Source
1. Create `app/services/ai/trend_scout/sources/new_source.py` with a `fetch_trending()` function
2. Register in `sources/__init__.py`
3. Add to `FETCHERS` in `services/ai/trend_scout/__init__.py`
4. Add to `_PROVIDER_CONFIG_CHECKS` in `blueprints/trend_scout/routes.py`
5. Add env var to `.env.example` and this doc

### Current Source Health Records

The `SourceHealthRecord` model links to `TrendReport` and stores:

- `source` — name string (e.g. `etsy`, `makerworld`)
- `status` — `success` or `error`
- `keyword` — last searched keyword or category slug
- `item_count` — number of items fetched
- `error_message` — error detail if status is error
- `scraped_at` — UTC timestamp of the fetch
- `metadata_json` — optional JSON blob for extended data
