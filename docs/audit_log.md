# Audit Log

The audit log records every meaningful action taken in DFPos. Events are
written to a dedicated microservice (`services/audit-log/`, port 8090)
and stored in their own Postgres database (`dfp_audit`). The Flask
application's main database never holds audit data.

## Architecture

```
┌──────────────────┐    POST /api/v1/audit-events    ┌──────────────────┐
│  Flask app       │ ─────────────────────────────► │  Audit-log       │
│  (web/worker)    │                                │  microservice    │
│                  │ ◄───── 201 Created ──────────── │  (FastAPI)       │
│  ┌────────────┐  │                                │                  │
│  │ AuditClient│  │  network/5xx failure           │  ┌────────────┐  │
│  │            │──┼─────► Redis outbox ──────────► │  │ Postgres   │  │
│  └────────────┘  │           (audit:outbox)       │  │ dfp_audit  │  │
│                  │                                │  └────────────┘  │
│                  │  Redis also down               │                  │
│                  │           ──► disk deadman ──► │  (next startup  │
│                  │              (uploads/         │   replays)       │
│                  │               audit-queue/)    │                  │
└──────────────────┘                                └──────────────────┘
         ▲
         │ Celery beat every 30s
         ▼
┌──────────────────┐
│  flush_audit_    │  Drains Redis → microservice
│  outbox task     │
└──────────────────┘
```

The audit client follows an **outbox-first** delivery model:

1. **Try direct POST.** Synchronous HTTP `POST /api/v1/audit-events`.
2. **On network error or 5xx**, push the event onto the Redis list
   `audit:outbox` (`RPUSH`).
3. **A Celery beat task** (`app.tasks.audit_outbox.flush_outbox`,
   `app.celery_app.make_celery`) drains the outbox every 30 seconds and
   replays each event through the direct path.
4. **If Redis is also unavailable**, the event is written to a
   `uploads/audit-queue/<timestamp>-<pid>-<action>.json` deadman file.
5. **On the next web boot** (`app/__init__.py:_replay_audit_outbox`)
   the deadman directory is replayed back onto Redis.

The microservice is configured in `docker-compose.yml` with:

- **`appendonly yes`** — Redis AOF is on so outbox writes are durable.
- **`appendfsync everysec`** — at most 1 second of writes can be lost
  on a hard crash.
- **`maxmemory-policy noeviction`** — the outbox cannot be silently
  dropped under memory pressure; Redis returns an error and the
  producer falls back to the deadman directory.

## Backpressure

`AUDIT_OUTBOX_MAX_SIZE` (default **100,000**) is the ceiling:

- **Below the ceiling**, every event is enqueued.
- **At or above the ceiling**:
  - **Critical events** (`critical=True`, e.g. `order.refunded`,
    `payment.recorded`) are **refused** and `AuditDispatchError` is
    raised if `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS=true`.
  - **Non-critical events** are written to the deadman directory.

A health warning is logged every time the ceiling is hit so operators
see it.

## What gets recorded

Every state-changing action in the app emits an event. The canonical
list lives in `app/utils/audit_events.py:AuditAction`. Highlights:

| Module | Events |
|---|---|
| **Auth / users** | `user.login_succeeded`, `user.login_failed`, `user.logout`, `user.password_changed`, `user.created`, `user.updated`, `user.deactivated`, `user.role_changed`, `api_token.created`, `api_token.revoked` |
| **Settings** | `setting.changed`, `feature_flag.changed`, `module.enabled`, `module.disabled`, `module.disabled_access_attempted`, `auth.failed_authorization` |
| **Products** | `product.created/updated/archived/restored`, `variant.*`, `model_asset.license_tracked` |
| **Inventory** | `inventory.adjusted/transferred/deducted/reserved/released/transfer_received/returned` |
| **Print jobs** | `print_job.created/updated/status_changed/failed/completed` |
| **Customers / orders** | `customer.*`, `order.*`, `payment.*`, `custom_request.*` |
| **POS** | `pos_session.opened/closed/voided`, `pos_sale.completed/voided/refunded` |
| **Markets** | `market.*`, `market_packing_list.*` |
| **Receipts / expenses** | `receipt.uploaded/extracted/parsed_by_ai/manually_edited/approved/rejected/archived`, `expense_ledger.*` |
| **Prep tasks** | `prep_task.generated/updated/completed/reopened` |
| **Cost engine** | `cost_engine.snapshot_recorded` |
| **Analytics** | `analytics.ai_insight_generated` |
| **API** | Every `/api/v1/...` `POST`/`PUT`/`PATCH`/`DELETE` is recorded by the global `after_request` hook in `app/__init__.py:_register_api_audit_hook` as `api.<verb>`. |

The list is enforced by the **coverage test** at
`tests/test_audit_coverage.py`. It runs in CI and fails if a state-changing
route or a documented `AGENTS.md` event is missing from the audit layer.

## Per-event payload

Each event is a JSON object stored in the microservice's `audit_events`
table. Every event captures the chain-verifiable fields below:

| Field | Source | Example |
|---|---|---|
| `id` | Server-assigned UUID v4 | `d17b7a71-ba7e-44c9-9ede-cccc38553051` |
| `occurred_at` | Caller wall-clock | `2026-08-13T04:31:59.095262Z` |
| `received_at` | Microservice wall-clock | `2026-08-13T04:31:59.125579Z` |
| `actor_id` | `flask_login.current_user.id` or token id | `1` |
| `actor_type` | `user`, `api_token`, `system`, `anonymous` | `user` |
| `actor_display_name` | `User.full_name` or email | `Dude Fish` |
| `action` | Dotted past-tense verb | `order.refunded` |
| `entity_type` | Affected entity | `order` |
| `entity_id` | Record id | `34` |
| `source_service` | Always `dfp-os` | `dfp-os` |
| `source_module` | Calling Python module | `app.blueprints.orders` |
| `request_id` | `X-Request-ID` header or generated UUID | `req-abc123` |
| `ip_address` | `X-Forwarded-For` or `request.remote_addr` | `10.0.0.7` |
| `user_agent` | `User-Agent` header | `Mozilla/5.0 ...` |
| `before_state` | Full row snapshot pre-change | `{"status": "draft", "total": "0.00"}` |
| `after_state` | Full row snapshot post-change | `{"status": "paid", "total": "29.99"}` |
| `metadata` | Free-form per-event data | `{"reason": "duplicate"}` |
| `hash` | SHA-256 chain hash | `b4797221...dda5f0` |
| `previous_hash` | Prior event's hash → tamper-evident chain | `5bb03629...f64c00` |

The `request_id`, `ip_address`, and `user_agent` are auto-captured by
`AuditClient._request_context` from `flask.g` (which is set by the
`before_request` hook in `app/__init__.py`). Background tasks pass
`request_id` explicitly because they have no HTTP context.

## How to use the API

### List recent events

```bash
curl -H "Authorization: Bearer $AUDIT_LOG_TOKEN" \
  "http://audit-log:8090/api/v1/audit-events?limit=50"
```

### Filter by entity

```bash
curl -H "Authorization: Bearer $AUDIT_LOG_TOKEN" \
  "http://audit-log:8090/api/v1/audit-events?entity_type=order&entity_id=34"
```

### View one event

```bash
curl -H "Authorization: Bearer $AUDIT_LOG_TOKEN" \
  "http://audit-log:8090/api/v1/audit-events/$EVENT_ID"
```

### Verify the integrity chain

```bash
curl -X POST -H "Authorization: Bearer $AUDIT_LOG_TOKEN" \
  "http://audit-log:8090/api/v1/audit-events/verify-chain"
```

### From the web UI

`/audit-logs/` lists recent events. Click any row to see the full
event detail (every field, before/after state, metadata, chain hash).

## Operational runbook

### Check the outbox size

```bash
docker exec dfpos-redis-1 redis-cli LLEN audit:outbox
```

A non-zero size means the microservice is (or was) unreachable and
the next beat tick will drain it. If the size is close to
`AUDIT_OUTBOX_MAX_SIZE`, raise the limit or scale the microservice.

### Replay the deadman directory manually

The deadman directory lives at `uploads/audit-queue/` inside the
`dfpos-web-1` container. To force a replay without a restart:

```bash
docker exec dfpos-web-1 python3 -c "
from app import create_app
from app.services import audit_outbox
app = create_app()
with app.app_context():
    print('replayed', audit_outbox.replay_deadman())
"
```

### Force a manual flush

```bash
docker exec dfpos-worker-1 celery -A app.celery_app.celery call \
  app.tasks.audit_outbox.flush_audit_outbox
```

### Detect a stuck chain

If a `verify-chain` call returns a mismatch, the events with a
`previous_hash` that doesn't match the prior event's `hash` are the
ones that were tampered with. They keep their original `hash` so
post-hoc analysis is still possible.

## Migrations

The audit-log microservice uses Alembic. The migration step is **not**
yet wired into `docker-compose.yml`. After a fresh deploy you must run:

```bash
docker exec dfpos-audit-log-1 alembic upgrade head
```

(Override `alembic.ini`'s `sqlalchemy.url` if the live URL is not the
default.) This is tracked in the production-readiness scorecard.

## Configuration reference

| Env var | Default | Meaning |
|---|---|---|
| `AUDIT_LOG_ENABLED` | `false` | Master switch. If `false`, the client is a no-op. |
| `AUDIT_LOG_BASE_URL` | `http://audit-log:8090` | Microservice base URL. |
| `AUDIT_LOG_TOKEN` | (empty) | Bearer token for the microservice API. |
| `AUDIT_LOG_FAIL_CLOSED` | `false` | Raise `AuditDispatchError` for **any** failed event. |
| `AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS` | `false` | Raise `AuditDispatchError` for failed `critical=True` events. |
| `AUDIT_REDIS_URL` | `redis://localhost:6379/0` | Outbox Redis. |
| `AUDIT_OUTBOX_KEY` | `audit:outbox` | Redis list key. |
| `AUDIT_OUTBOX_MAX_SIZE` | `100000` | Backpressure ceiling. |
| `AUDIT_OUTBOX_FLUSH_INTERVAL_SECONDS` | `30` | Beat schedule. |
| `AUDIT_OUTBOX_BATCH_SIZE` | `200` | Events drained per beat tick. |
| `AUDIT_OUTBOX_DLQ_PATH` | `uploads/audit-queue` | Deadman directory. |
