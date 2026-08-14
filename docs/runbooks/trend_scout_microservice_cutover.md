# Trend Scout Microservice — Cutover Runbook

This runbook walks the operator through cutting the Trend Scout admin UI off
the monolithic Flask DB and onto the new `services/trend-scout` microservice.

## Why this runbook exists

The Trend Scout pipeline moved from the Flask app into the microservice over
phases 0–5. Phase 6 is the cutover itself: the Flask admin UI now reads
trend data from the microservice over HTTP via
`app.services.trend_scout_proxy.TrendScoutProxy`. The microservice is the
new source of truth for `trend_reports`, `trend_snapshots`,
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
   - `TREND_SCOUT_CELERY_QUEUE=trend_scout`, `TREND_SCOUT_CELERY_TASK_PRIORITY=1`
6. **Existing data is captured (optional)** — Phase 6 ships with no rows in
   the trend tables per the plan; if you ran an old pipeline before
   cutting over, those rows are still in `dfp_trend_scout` and remain queryable.

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
   docker compose exec web flask --app app:create_app trend-scout-cli run  # legacy CLI removed in Phase 6
   # or via the Flask proxy that the admin UI now uses:
   curl -fsS -H "Authorization: Bearer $TREND_SCOUT_INTERNAL_API_TOKEN" \
     -X POST http://localhost:8093/api/v1/pipeline/run
   ```

   The pipeline enqueues on the `trend_scout` queue at priority 1. The
   dedicated worker consumes it; the main app's worker also drains it but
   never preempts higher-priority tasks.

3. **Switch the Flask proxy on**:

   The Flask admin UI reads through `app.services.trend_scout_proxy`
   starting with this PR. No additional flag is needed. If you want to
   confirm the proxy works without disturbing anything, hit an admin route:

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

5. **Watch the queue behavior for one week**:

   ```bash
   docker compose exec redis redis-cli -n 1 LLEN "trend_scout"
   docker compose exec redis redis-cli -n 1 ZRANGE "celery@..b" 0 -1
   ```

   Trend Scout should never preempt audit_outbox, model_analysis, or
   cost_calculation. If it does, file a follow-up issue referencing the
   `task_queue_max_priority=10` configuration.

## Rollback

The microservice runs alongside the Flask app; nothing in the monolith was
deleted before Phase 6 ships. Rollback path:

1. **Stop dispatching to the microservice** — set
   `TREND_SCOUT_SERVICE_URL=http://localhost:0` (or any unreachable URL). The
   `TrendScoutProxy.TrendScoutUnavailable` exception will surface 503s in the
   admin UI, which is what you want during a rollback to avoid partial reads.
2. **If you need the old DB tables back**: they were NOT deleted in Phase 6
   (cuts over behind the proxy only). Flip `app.blueprints.trend_scout.routes`
   import back to the previous git revision and restart the web container.

## What got deleted in Phase 6

Phase 6's hard-cutover step deletes:

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
  — admin-only helpers; follow-up work in Phase 10.
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
4. **Pipeline run progress**. The admin UI shows `current_step` from the
   in-memory task monitor (`app.workers.task_monitor`). A Redis-backed
   monitor is a Phase 10 follow-up.

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
