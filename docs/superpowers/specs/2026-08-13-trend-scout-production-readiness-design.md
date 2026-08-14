# Trend Scout Production Readiness Design

**Date:** 2026-08-13
**Branch:** `phase/10-hardening-and-scorecard`
**Status:** Approved for implementation

## Goal

Make Trend Scout production-ready as a self-contained DFPos capability, including the Trend Scout microservice, Flask proxy/admin consumers, Product Studio trend-score lookup, Firecrawl adapter profile, deployment runbook, and focused verification gates.

## Scope

In scope:

- `services/trend-scout` FastAPI API, Celery worker, Redis integration, tests, and Docker deployment path.
- Flask-side `app.services.trend_scout_proxy` and routes that depend on it.
- Product Studio trend-score lookup that consumes Trend Scout data.
- Firecrawl adapter readiness where Trend Scout depends on it.
- Production runbook, scorecard, and verification commands.

Out of scope:

- Full DFPos platform production readiness outside Trend Scout.
- SaaS tenancy, billing, or real card processing.
- Full upstream Firecrawl vendoring. The current internal adapter remains the production target for this pass.
- Automatic migration of old deleted monolith Trend Scout rows unless a pre-cutover database dump is provided.

## Architecture

Trend Scout remains a microservice-backed module. The Flask app must not query old Trend Scout ORM tables or source/analyzer services. All Trend Scout UI and Product Studio score requests go through `TrendScoutProxy` to the FastAPI service.

The main hardening gap is task-run visibility. Production cannot rely on process-local memory because API and worker containers are separate processes and can restart independently. Task-run state will move to Redis using `TREND_SCOUT_REDIS_URL`, while preserving the existing `create_task_run`, `start_task_run`, `update_task_progress`, `complete_task_run`, `get_task_run`, and `list_task_runs` interfaces.

Pipeline enqueue will create a visible queued run immediately, keyed by both Celery task ID and logical `run_id`. Worker progress will update the same logical run record. API status endpoints will resolve by either `run_id`, Celery task ID, or internal pipeline task ID and will return meaningful progress from completed and total step counts.

## Components

- `services/trend-scout/app/workers/task_monitor.py`: Redis-backed task monitor with JSON records, sorted index, retention limit, and safe fallback for tests/local failures.
- `services/trend-scout/app/api/routes/pipeline.py`: enqueue-time run creation, reliable lookup, progress response, and cancel status updates.
- `services/trend-scout/app/services/pipeline_runner.py`: update existing queued records rather than creating disconnected process-local records.
- `services/trend-scout/app/workers/tasks.py`: pass Celery task ID into the pipeline runner so API-created records and worker progress refer to the same run.
- `services/trend-scout/app/tests/`: focused tests for Redis persistence and pipeline API behavior.
- `tests/test_trend_scout_proxy.py`: maintain Flask proxy coverage for dependent surfaces.
- `docs/runbooks/trend_scout_microservice_cutover.md`: final production runbook.
- `docs/production_readiness_scorecard.md`: evidence-based Trend Scout readiness update.

## Data Flow

1. Admin clicks run pipeline in Flask.
2. Flask calls `POST /api/v1/pipeline/run` on the Trend Scout service through `TrendScoutProxy`.
3. FastAPI enqueues Celery, then records a Redis task-run with `run_id`, Celery `task_id`, trigger, status `queued`, and metadata.
4. Celery worker starts `trend_scout_pipeline` and calls `run_full_pipeline` with the same `run_id` and Celery task ID.
5. Pipeline runner updates Redis progress as steps complete.
6. Flask polls `/api/v1/pipeline/status/{run_id}` and renders progress from Redis.
7. `/api/v1/pipeline/runs` and `/runs/{id}` show recent persisted task-run state across API/worker restarts.

## Error Handling

- If Redis is unavailable in production, task monitor writes should log warnings and use an in-process fallback only to avoid crashing the pipeline. The runbook will treat Redis outage as degraded production state.
- If Celery enqueue fails, `/pipeline/run` returns `503` and does not claim the run is queued.
- If cancel is requested for a known run, Celery revoke is attempted and the Redis task-run status is updated to `revoked`.
- If a run is unknown, status returns `unknown`; detail endpoints return `404`.

## Verification Gates

Trend Scout can be called production-ready only after fresh evidence from:

- `cd services/trend-scout && uv run ruff check .`
- `cd services/trend-scout && uv run ruff format --check .`
- `cd services/trend-scout && uv run pytest -q -m 'not slow'`
- `cd services/firecrawl && uv run --extra dev ruff check .`
- `cd services/firecrawl && uv run --extra dev ruff format --check .`
- `cd services/firecrawl && uv run --extra dev pytest -q`
- `uv run pytest -q tests/test_trend_scout_proxy.py`
- `uv run pytest --collect-only -q`
- Flask app boot check through `create_app()`.
- Docker compose config with required placeholder environment.
- Sequential Docker build for the shared Trend Scout image and Firecrawl image.

## Known Non-Blocking Limitations

- Old monolith Trend Scout rows are not migrated automatically because the monolith implementation has been deleted. If those rows are valuable, export from a pre-cutover revision.
- The internal Firecrawl adapter intentionally implements a narrow compatible API for Trend Scout. It is not a full upstream Firecrawl replacement.
- Full main-app DB-backed tests may remain blocked by local database credentials. That blocker must be documented separately and cannot be used as evidence for unrelated modules.
