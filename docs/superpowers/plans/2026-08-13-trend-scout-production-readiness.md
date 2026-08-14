# Trend Scout Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Trend Scout production-ready by hardening task-run persistence, run control semantics, dependent Flask surfaces, deployment docs, and verification gates.

**Architecture:** Trend Scout remains a FastAPI/Celery microservice consumed by Flask through `TrendScoutProxy`. Redis becomes the source of truth for task-run monitor state so the API and worker containers share progress, cancellation, retry, and recent-run visibility.

**Tech Stack:** Python 3.14, FastAPI, Celery, Redis, SQLAlchemy async, Flask proxy, pytest, Ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-13-trend-scout-production-readiness-design.md`

## Global Constraints

- Use Python 3.14 and `uv` for Python commands.
- Preserve the Trend Scout microservice as source of truth; do not reintroduce old Flask Trend Scout ORM/services/tasks.
- Keep Firecrawl as the internal production-buildable adapter for this pass.
- Do not hardcode secrets.
- Keep edits minimal and production-minded.
- Do not modify unrelated local changes in `.dockerignore`, `.gitignore`, or session files.
- Commit frequently after verified increments.

---

### Task 1: Redis-Backed Task Monitor

**Files:**
- Modify: `services/trend-scout/app/workers/task_monitor.py`
- Test: `services/trend-scout/app/tests/test_celery_and_streams.py`

**Interfaces:**
- Consumes: `app.config.settings.redis_url`
- Produces: existing functions `create_task_run`, `start_task_run`, `update_task_progress`, `complete_task_run`, `get_task_run`, `list_task_runs`

- [ ] **Step 1: Write tests for shared persistent monitor behavior**

Add tests that monkeypatch the monitor Redis client to a fake Redis object and verify:

```python
def test_task_monitor_persists_records_to_redis(monkeypatch):
    create_task_run("task-redis-1", trigger="manual", total_steps=4, run_id="run-1")
    start_task_run("task-redis-1")
    update_task_progress("task-redis-1", completed_steps=2, current_step="analyzing")
    run = get_task_run("run-1")
    assert run["task_id"] == "task-redis-1"
    assert run["run_id"] == "run-1"
    assert run["completed_steps"] == 2
    assert run["progress"] == 50.0
```

Also verify lookup by task ID still works and `list_task_runs()` is sorted by recency.

- [ ] **Step 2: Run the focused tests to confirm they fail**

Run: `cd services/trend-scout && uv run pytest -q app/tests/test_celery_and_streams.py -k task_monitor`

Expected: FAIL because the monitor is still in-memory and lacks Redis/fallback test hooks and progress calculation.

- [ ] **Step 3: Implement Redis-backed monitor**

Implement JSON records stored under keys like `trend_scout:task_runs:{task_id}`, alias keys for `run_id`, and a sorted set `trend_scout:task_runs:index`. Keep an in-memory fallback path when Redis is unavailable.

- [ ] **Step 4: Run the focused tests to confirm they pass**

Run: `cd services/trend-scout && uv run pytest -q app/tests/test_celery_and_streams.py -k task_monitor`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `Harden Trend Scout task monitor persistence`

### Task 2: Pipeline Run Visibility and Control

**Files:**
- Modify: `services/trend-scout/app/api/routes/pipeline.py`
- Modify: `services/trend-scout/app/services/pipeline_runner.py`
- Modify: `services/trend-scout/app/workers/tasks.py`
- Test: `services/trend-scout/app/tests/test_api.py`
- Test: `services/trend-scout/app/tests/test_celery_and_streams.py`

**Interfaces:**
- Consumes: task monitor functions from Task 1
- Produces: `/api/v1/pipeline/run`, `/status/{run_id}`, `/runs`, `/runs/{run_id}`, `/cancel/{run_id}` with reliable shared state

- [ ] **Step 1: Add API tests for enqueue-time visibility and lookup**

Add tests verifying that after mocked Celery enqueue, `/pipeline/run` creates a queued run and `/pipeline/status/{run_id}` returns `queued` with `0.0` progress.

- [ ] **Step 2: Add API tests for lookup by Celery task ID and cancel status**

Verify `/pipeline/runs/{task_id}` and `/pipeline/runs/{run_id}` both resolve, and cancel changes a known run to `revoked`.

- [ ] **Step 3: Run the focused tests to confirm they fail**

Run: `cd services/trend-scout && uv run pytest -q app/tests/test_api.py app/tests/test_celery_and_streams.py -k 'pipeline or task_monitor'`

Expected: FAIL on enqueue-time visibility and cancel status.

- [ ] **Step 4: Implement run visibility and progress semantics**

Create the queued task-run record in `run_pipeline` after successful Celery enqueue. Update `run_full_pipeline` to accept `task_id` and update an existing record rather than creating a disconnected internal-only record. Compute progress as `completed_steps / total_steps * 100`.

- [ ] **Step 5: Run the focused tests to confirm they pass**

Run: `cd services/trend-scout && uv run pytest -q app/tests/test_api.py app/tests/test_celery_and_streams.py -k 'pipeline or task_monitor'`

Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `Stabilize Trend Scout pipeline run state`

### Task 3: Flask Dependent Surface Verification

**Files:**
- Modify if needed: `app/services/trend_scout_proxy.py`
- Modify if needed: `app/blueprints/trend_scout/routes.py`
- Modify if needed: `app/blueprints/products/studio_routes.py`
- Test: `tests/test_trend_scout_proxy.py`

**Interfaces:**
- Consumes: Trend Scout API behavior from Task 2
- Produces: stable Flask proxy behavior for admin and Product Studio consumers

- [ ] **Step 1: Run existing proxy tests**

Run: `uv run pytest -q tests/test_trend_scout_proxy.py`

Expected: PASS or expose proxy gaps caused by Task 2.

- [ ] **Step 2: Add focused tests only if a gap is found**

If proxy behavior does not cover task-run status/cancel/retry or Product Studio failure handling, add minimal tests to `tests/test_trend_scout_proxy.py`.

- [ ] **Step 3: Fix any failing proxy behavior minimally**

Keep all Flask reads through `TrendScoutProxy`; do not import old Trend Scout models/services.

- [ ] **Step 4: Run proxy tests again**

Run: `uv run pytest -q tests/test_trend_scout_proxy.py`

Expected: PASS.

- [ ] **Step 5: Commit if files changed**

Commit message: `Verify Trend Scout Flask proxy surfaces`

### Task 4: Production Docs and Runbook

**Files:**
- Modify: `docs/runbooks/trend_scout_microservice_cutover.md`
- Modify: `docs/production_readiness_scorecard.md`
- Modify if needed: `docs/trend_scout_microservice_plan.md`

**Interfaces:**
- Consumes: implementation behavior from Tasks 1-3
- Produces: accurate production runbook and scorecard evidence

- [ ] **Step 1: Update runbook**

Document Redis-backed task monitor, release migration, sequential Docker build command for the shared Trend Scout image, Firecrawl adapter profile, smoke checks, rollback, and degraded modes.

- [ ] **Step 2: Update scorecard**

Update the Trend Scout production cutover section to reflect verified Redis-backed monitor and final validation commands. Do not claim full DFPos readiness.

- [ ] **Step 3: Commit docs**

Commit message: `Document Trend Scout production readiness gates`

### Task 5: Final Verification and Push

**Files:**
- No code changes unless verification finds a defect.

**Interfaces:**
- Consumes: all previous tasks
- Produces: evidence that Trend Scout and touched dependencies are production-ready

- [ ] **Step 1: Trend Scout service checks**

Run: `cd services/trend-scout && uv run ruff check . && uv run ruff format --check . && uv run pytest -q -m 'not slow'`

- [ ] **Step 2: Firecrawl adapter checks**

Run: `cd services/firecrawl && uv run --extra dev ruff check . && uv run --extra dev ruff format --check . && uv run --extra dev pytest -q`

- [ ] **Step 3: Flask dependent checks**

Run: `uv run pytest -q tests/test_trend_scout_proxy.py`

Run: `uv run pytest --collect-only -q`

Run: `uv run python -c "from app import create_app; app=create_app(); print(len(app.url_map._rules))"`

- [ ] **Step 4: Docker checks**

Run compose config with placeholder environment and `--profile firecrawl`.

Run: `docker compose build trend-scout`

Run: `docker compose --profile firecrawl build firecrawl-api`

- [ ] **Step 5: Update docs if final evidence differs**

If any check is blocked by environment, document the exact blocker and do not claim that check passed.

- [ ] **Step 6: Push**

Run: `git status`, `git diff`, `git log --oneline -10`, then push committed changes.
