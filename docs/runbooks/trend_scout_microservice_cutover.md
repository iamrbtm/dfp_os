# Trend Scout Microservice — Cutover Runbook

This runbook walks the operator through running Trend Scout after the completed
cutover from the monolithic Flask DB to the `services/trend-scout` microservice.

## Why this runbook exists

The Trend Scout pipeline moved from the Flask app into the microservice over
phases 0–10, then this production pass completed the hard cutover. The Flask
admin UI and Trend Scout-specific Flask API actions now read trend data from
the microservice over HTTP via `app.services.trend_scout_proxy.TrendScoutProxy`.
The microservice is the source of truth for `trend_reports`, `trend_snapshots`,
`trend_opportunity_scores`, `source_health_records`, `trend_weights`, and
task-run state.

## Pre-flight (before you cut over)

1. **Microservice image is built and pushed** — `services/trend-scout`
   builds successfully with `docker compose build trend-scout`.
2. **Database is provisioned** — the `trend_scout` logical DB exists on the
   shared Postgres. The init script (`docker/postgres/init/01-init-databases.sh`)
   provisions it on a fresh DB cluster; for existing DBs run:
   ```sql
   CREATE DATABASE dfp_trend_scout;
   CREATE USER dfp_trend_scout WITH PASSWORD 'set-via-env';
   GRANT ALL PRIVILEGES ON DATABASE dfp_trend_scout TO dfp_trend_scout;
   ```
3. **Alembic migrations applied** — `docker compose run --rm trend-scout-migrate`
   runs `alembic upgrade head` against the logical DB.
4. **Celery worker is up** — `trend-scout-worker` container is running and
   subscribed to the `trend_scout` queue.
5. **Env vars set**:
   - `TREND_SCOUT_SERVICE_URL=http://trend-scout:8093` (set in `x-env-app` already)
   - `TREND_SCOUT_INTERNAL_API_TOKEN` — shared between the Flask app and the microservice
   - `TREND_SCOUT_REDIS_URL=redis://redis:6379/2` — shared task-run monitor and Redis Streams state
   - `TREND_SCOUT_CELERY_QUEUE=trend_scout`, `TREND_SCOUT_CELERY_TASK_PRIORITY=1`
6. **Existing monolith data migration** — there is no automatic migration from
   deleted Flask tables to the microservice DB. If old trend rows were valuable,
   export them from a pre-cutover revision before deploying this branch.

## Cutover steps

The cutover is env-driven. No code changes are needed at runtime.

1. **Deploy the microservice stack first**:

   ```bash
   docker compose up -d trend-scout trend-scout-worker
   docker compose run --rm trend-scout-migrate
   ```

   Verify:
   ```bash
   curl -fsS http://localhost:8093/health/live | jq
   # {"status":"alive","service":"dfp-trend-scout","version":"0.1.0"}
   ```

2. **Run the first pipeline from the new microservice**:

   ```bash
   RUN_RESPONSE=$(curl -fsS -H "Authorization: Bearer $TREND_SCOUT_INTERNAL_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"trigger":"production-smoke"}' \
      -X POST http://localhost:8093/api/v1/pipeline/run)
   echo "$RUN_RESPONSE" | jq
   ```

   The pipeline enqueues on the `trend_scout` queue at priority 1. The
   dedicated worker consumes it; the main app's worker also drains it but
   never preempts higher-priority tasks.

   Verify the queued run is visible before the worker starts processing:

   ```bash
   RUN_ID=$(echo "$RUN_RESPONSE" | jq -r .run_id)
   curl -fsS -H "Authorization: Bearer $TREND_SCOUT_INTERNAL_API_TOKEN" \
      "http://localhost:8093/api/v1/pipeline/status/$RUN_ID" | jq
   curl -fsS -H "Authorization: Bearer $TREND_SCOUT_INTERNAL_API_TOKEN" \
      "http://localhost:8093/api/v1/pipeline/runs/$RUN_ID" | jq
   ```

3. **Verify the Flask proxy**:

   The Flask admin UI reads through `app.services.trend_scout_proxy`. No
   additional flag is needed. If you want to confirm the proxy works without
   disturbing anything, hit an admin route:

   ```bash
   # Login, then:
   curl -fsS -b cookies.txt http://localhost:5000/admin/trend-scout/
   ```

   The page will render from the microservice data. Empty reports are
   expected on first boot until the pipeline has run.

4. **Verify source health shows the microservice runs**:

   ```bash
    curl -fsS -H "Authorization: Bearer $TREND_SCOUT_INTERNAL_API_TOKEN" \
      http://localhost:8093/api/v1/source-health
    ```

    Some sources are intentionally credential- or network-dependent:
    - `internal_demand` should be `success` when `TREND_SCOUT_INTERNAL_API_TOKEN`
      is shared by Flask and the microservice.
    - `reddit` may be `degraded` when it returns useful RSS items but some feeds
      rate-limit with `HTTP 429`.
    - `etsy`, `pinterest`, and `tiktok` require `ETSY_API_KEY`,
      `PINTEREST_API_KEY`, and approved `TIKTOK_RESEARCH_ACCESS_TOKEN` values.
    - `last30days` requires `LAST30DAYS_RAW_FILE` to point at a readable raw
      research markdown file inside the container.
    - `bgg` and `printables` can return upstream Cloudflare/auth challenges from
      Docker networks. Treat those as external blocking unless a compliant API or
      explicitly enabled scrape adapter is configured.

5. **Watch the queue behavior for one week**:

   ```bash
   docker compose exec redis redis-cli -n 1 LLEN "trend_scout"
   docker compose exec redis redis-cli -n 1 ZRANGE "celery@..b" 0 -1
   ```

   Trend Scout should never preempt audit_outbox, model_analysis, or
   cost_calculation. If it does, file a follow-up issue referencing the
   `task_queue_max_priority=10` configuration.

## Rollback

The hard cutover deletes the legacy Flask Trend Scout implementation. Rollback
requires reverting to the previous git revision or restoring from backup.

1. **Stop writes** — stop `trend-scout-worker` first so no new reports are
   generated during rollback.
2. **Revert application code** — deploy the last pre-hard-cutover commit if you
   need the old Flask tables and CLI back.
3. **Restore old database tables if needed** — use database backups/migrations
   from the pre-cutover deployment. The current branch no longer maps those
   tables in SQLAlchemy.

## What got deleted in Phase 6

The completed hard-cutover deletes:

- `app/models/trend.py` — TrendSnapshot / TrendReport / TrendOpportunityScore /
  SourceHealthRecord / TrendCalibrationResult / TrendWeight / TrendReportHistory
  ORM models. The data they referenced now lives in the `trend_scout` DB.
- `app/services/ai/trend_scout/` — the entire Trend Scout service folder
  (sources / analyzer / pipeline runner). Replaced by `services/trend-scout/`.
- `app/services/trend_scout_weights.py` — replaced by
  `services/trend-scout/app/services/weights.py`.
- `app/services/trend_scout_backtest.py` — replaced by
  `services/trend-scout/app/services/backtest.py`.
- `app/services/trend_scout_calibration.py` — replaced by
  `services/trend-scout/app/services/calibration.py`.
- `app/services/trend_scout_history.py` and `app/services/trend_scout_prune.py`
   — replaced by microservice endpoints and Flask proxy view-model shims.
- `app/tasks/trend_scout.py` and `app/tasks/trend_calibration.py` — replaced
  by `app/tasks/dispatch_trend_scout.py` which POSTs to the microservice.

## What the operator should monitor in production

1. **Source health rows land in the microservice DB**, not the main app DB.
   The admin UI reads them via the proxy. Verify rows are written by hitting
   `/api/v1/source-health` with the internal token.
2. **Audit events continue to dispatch to `audit-log`**. The microservice
   uses `app.services.audit_dispatch.dispatch_audit_event` which forwards to
   the audit-log microservice on `http://audit-log:8090`.
3. **Celery queue separation**. Run `celery -A app.celery_app.celery inspect
   stats` and confirm the dedicated `trend-scout-worker` is registered. If the
   main `worker` container drains `trend_scout` before the dedicated worker,
   the dedicated worker is starved — Phase 10 surfaces that as a metric.
4. **Pipeline run progress**. The admin UI shows `current_step` and progress
   from the Redis-backed microservice task monitor. The API and worker share
   records through `TREND_SCOUT_REDIS_URL`, so queued/running/completed/failed/
   revoked state survives container boundaries. A Redis outage is degraded
   production state; the service falls back to process-local memory only to keep
   the pipeline from crashing.

## Production Verification Gate

Run these checks before calling Trend Scout production-ready on a deployment:

```bash
cd services/trend-scout
uv run ruff check .
uv run ruff format --check .
uv run pytest -q -m 'not slow'

cd ../firecrawl
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev pytest -q

cd ../..
uv run pytest -q tests/test_trend_scout_proxy.py
uv run pytest --collect-only -q
uv run python -c "from app import create_app; app=create_app(); print(len(app.url_map._rules))"
```

Docker build note: `trend-scout` and `trend-scout-worker` share the same image
tag (`dfpos-trend-scout:local`). Build the shared image once instead of building
both services concurrently:

```bash
docker compose build trend-scout
docker compose --profile firecrawl build firecrawl-api
```

## Firecrawl Adapter

The `firecrawl` compose profile now starts a production-buildable internal
adapter at `services/firecrawl`, not an incomplete upstream Firecrawl checkout.
Enable it with:

```bash
FIRECRAWL_API_KEY=change-me docker compose --profile firecrawl up -d firecrawl-api
```

The adapter exposes `/health`, `/v2/scrape`, and `/v2/search`. Search returns an
empty result by design; Trend Scout uses configured target URLs to control crawl
scope. The upstream Firecrawl sidecars remain under the separate
`firecrawl-upstream` profile for future vendor work only.

## Common questions

- **Why is the microservice on its own port (`8093`) and not behind the same
  reverse proxy?** The microservice serves internal-only endpoints; exposing
  them publicly would let anyone with the token scrape internal demand data.
  The Flask proxy at `/admin/trend-scout/*` is the only public surface.
- **Why does Trend Scout run on a low-priority queue?** Per design: a busy
  market vendor should never be slowed by a weekly trend report running in
  parallel. Main app tasks (audit outbox flush, model analysis) take priority.
- **Can I run the microservice without the dedicated worker?** Yes — the main
   `worker` container's command includes `-Q celery,trend_scout`. The dedicated
   worker is added for capacity isolation; removing it does not break the queue.

## Troubleshooting

- **I ran the pipeline but only see `app.tasks.audit_outbox.flush_outbox` in the
  worker log.** Check the correct containers first:

  ```bash
  docker compose ps trend-scout trend-scout-worker worker beat
  docker compose logs --since=10m trend-scout trend-scout-worker
  ```

  The heavy Trend Scout task is `app.workers.tasks.trend_scout_pipeline` and it
  appears in `trend-scout-worker`, not necessarily the main Flask `worker`. If
  `trend-scout` and `trend-scout-worker` are absent from `docker compose ps`,
  start them and run migrations:

  ```bash
  docker compose build trend-scout
  docker compose --profile release run --rm trend-scout-migrate
  docker compose up -d trend-scout trend-scout-worker
  ```

  The app also guards audit startup replay so Celery task app creation does not
  recursively enqueue `flush_outbox` tasks. If audit flushes still appear every
  second, inspect `AUDIT_OUTBOX_FLUSH_INTERVAL_SECONDS` and ensure only one beat
  container is running.
