You are working inside the DFP OS codebase.

Goal:
Build a production-ready Audit Log microservice for DFP OS.

This audit log must be a standalone internal microservice. It should be stateless, private, append-only, secure, and ready to scale later, but DO NOT add a load balancer in this phase.

Use this stack:

- Python 3.14
- uv
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x async ORM/core
- asyncpg
- Alembic
- PostgreSQL
- Redis Streams
- OpenTelemetry-ready structure
- Docker Compose
- pytest
- pytest-asyncio
- httpx
- ruff
- mypy

Important:
Do not use Pydantic v1.
Do not use Flask.
Do not use Django.
Do not use MongoDB.
Do not use Kafka, Redpanda, RabbitMQ, or NATS in this phase.
Do not add a load balancer.
Do not expose this service publicly.
Do not add update or delete endpoints for audit events.

The service should be designed so that a load balancer can be added later, but it should not require one now.

Architecture:
DFP OS app/modules call the Audit Log microservice over internal Docker Compose networking.

Default local architecture:

DFP OS app
  -> audit-log-service
  -> PostgreSQL

Optional async flow:

DFP OS app
  -> audit-log-service
  -> Redis Streams
  -> audit worker
  -> PostgreSQL

For v1, support both direct database writes and Redis Stream based ingestion, but keep the default path simple and reliable.

Suggested repository structure:

services/
  audit-log/
    pyproject.toml
    uv.lock
    Dockerfile
    README.md
    .env.example
    alembic.ini
    alembic/
      env.py
      versions/
    app/
      __init__.py
      main.py
      config.py
      database.py
      security.py
      telemetry.py
      models/
        __init__.py
        audit_event.py
      schemas/
        __init__.py
        audit_event.py
        health.py
      api/
        __init__.py
        deps.py
        routes/
          __init__.py
          health.py
          audit_events.py
      services/
        __init__.py
        audit_writer.py
        audit_search.py
        hashing.py
        redis_streams.py
      workers/
        __init__.py
        audit_stream_worker.py
      tests/
        test_health.py
        test_create_audit_event.py
        test_search_audit_events.py
        test_hash_chain.py
        test_idempotency.py

Create or update docker-compose.yml to include:
- audit-log-service
- audit-postgres
- audit-redis

No Nginx.
No Traefik.
No Caddy.
No load balancer.

The audit service must only be reachable over the internal Docker network.

Environment variables:
Create a .env.example with:

AUDIT_SERVICE_ENV=local
AUDIT_SERVICE_NAME=dfp-audit-log
AUDIT_API_HOST=0.0.0.0
AUDIT_API_PORT=8090

AUDIT_DATABASE_URL=postgresql+asyncpg://dfp_audit:dfp_audit_password@audit-postgres:5432/dfp_audit
AUDIT_REDIS_URL=redis://audit-redis:6379/0

AUDIT_INTERNAL_API_TOKEN=change-me-local-token
AUDIT_HASH_SECRET=change-me-local-hash-secret

AUDIT_USE_REDIS_STREAM=false
AUDIT_STREAM_NAME=dfp.audit.events
AUDIT_STREAM_CONSUMER_GROUP=audit-log-writers
AUDIT_STREAM_CONSUMER_NAME=audit-worker-1

AUDIT_LOG_LEVEL=INFO

Database model:
Create an append-only audit_events table.

Fields:
- id: UUID primary key
- idempotency_key: nullable string, unique when present
- tenant_id: nullable string
- occurred_at: timestamptz, required
- received_at: timestamptz, required, default now
- actor_id: nullable string
- actor_type: nullable string
- actor_display_name: nullable string
- action: required string
- entity_type: required string
- entity_id: nullable string
- source_service: required string
- source_module: nullable string
- request_id: nullable string
- correlation_id: nullable string
- ip_address: nullable string
- user_agent: nullable string
- before_state: JSONB nullable
- after_state: JSONB nullable
- metadata: JSONB nullable
- hash: required string
- previous_hash: nullable string

Indexes:
- occurred_at
- tenant_id
- actor_id
- action
- entity_type, entity_id
- source_service
- request_id
- correlation_id
- idempotency_key unique where not null

The audit table is append-only.
There must be no update endpoint.
There must be no delete endpoint.
Do not implement soft deletes either.

Hashing:
Implement tamper-evident hash chaining.

Each event hash should be generated using HMAC-SHA256 with AUDIT_HASH_SECRET.

The hash should include stable serialized values from:
- id
- occurred_at
- received_at
- tenant_id
- actor_id
- actor_type
- action
- entity_type
- entity_id
- source_service
- source_module
- request_id
- correlation_id
- before_state
- after_state
- metadata
- previous_hash

Use deterministic JSON serialization:
- sort keys
- compact separators
- consistent datetime formatting

For previous_hash:
- Get the most recent audit event hash for the same tenant_id when tenant_id exists.
- If tenant_id is null, get the most recent global hash.
- If no previous event exists, previous_hash is null.

Concurrency:
Be careful with hash chaining race conditions.
Use a transaction.
Use a reasonable locking strategy so two concurrent writes for the same tenant do not silently create broken hash chains.
Keep it simple and reliable.

API endpoints:

1. GET /health/live
Returns:
{
  "status": "alive",
  "service": "dfp-audit-log"
}

This should not check the database.

2. GET /health/ready
Returns ready only if:
- database connection works
- Redis check works only when AUDIT_USE_REDIS_STREAM=true

3. POST /api/v1/audit-events
Creates a single audit event.

Auth:
Requires internal service token.

Header:
Authorization: Bearer <AUDIT_INTERNAL_API_TOKEN>

Request body:
{
  "idempotency_key": "optional-string",
  "tenant_id": "optional-string",
  "occurred_at": "2026-06-15T10:00:00Z",
  "actor_id": "user-123",
  "actor_type": "user",
  "actor_display_name": "Jeremy",
  "action": "inventory.item.updated",
  "entity_type": "inventory_item",
  "entity_id": "item-123",
  "source_service": "dfp-os",
  "source_module": "inventory",
  "request_id": "req-123",
  "correlation_id": "corr-123",
  "ip_address": "127.0.0.1",
  "user_agent": "optional",
  "before_state": {},
  "after_state": {},
  "metadata": {}
}

Response:
{
  "id": "...",
  "received_at": "...",
  "hash": "...",
  "previous_hash": "..."
}

Behavior:
- If idempotency_key already exists, return the existing event instead of creating a duplicate.
- Validate required fields.
- Reject huge payloads with a clear 413 or 422 style response.
- Never allow client to submit hash or previous_hash.

4. POST /api/v1/audit-events/batch
Creates multiple audit events.

Rules:
- Max batch size: 100
- All events are validated individually.
- Return created event IDs.
- If one event is invalid, reject the whole batch.
- Respect idempotency keys.

5. GET /api/v1/audit-events
Search audit events.

Query filters:
- tenant_id
- actor_id
- actor_type
- action
- entity_type
- entity_id
- source_service
- source_module
- request_id
- correlation_id
- occurred_from
- occurred_to
- limit
- offset

Rules:
- Default limit: 50
- Max limit: 500
- Sort newest first by occurred_at, then received_at

6. GET /api/v1/audit-events/{id}
Return one audit event by ID.

7. GET /api/v1/entities/{entity_type}/{entity_id}/timeline
Return timeline for one entity.

Filters:
- tenant_id optional
- occurred_from optional
- occurred_to optional
- limit optional
- offset optional

8. GET /api/v1/actors/{actor_id}/timeline
Return timeline for one actor.

Filters:
- tenant_id optional
- occurred_from optional
- occurred_to optional
- limit optional
- offset optional

9. POST /api/v1/audit-events/verify-chain
Verify hash chain integrity.

Request:
{
  "tenant_id": "optional-string",
  "occurred_from": "optional-date",
  "occurred_to": "optional-date"
}

Response:
{
  "valid": true,
  "checked_count": 123,
  "first_invalid_event_id": null
}

Security:
- Use internal bearer token auth for all /api/v1 endpoints.
- Health endpoints do not need auth.
- Do not expose this service outside Docker internal networking.
- Never log full before_state or after_state by default.
- Avoid storing secrets in audit metadata.
- Add clear comments warning future developers not to log passwords, payment card data, full tokens, or other sensitive secrets.

Pydantic schemas:
Create strong request and response models.

Actions:
Use action names like:
- inventory.item.created
- inventory.item.updated
- inventory.item.deleted
- market.created
- market.updated
- market.deleted
- sale.created
- sale.completed
- sale.voided
- expense.created
- expense.updated
- expense.deleted
- user.login
- user.logout
- settings.updated

Do not hard-code these as the only valid choices. Allow custom action strings because DFP OS will grow.

Redis Streams:
Implement Redis stream publishing and worker support, but keep it optional.

When AUDIT_USE_REDIS_STREAM=false:
- POST endpoint writes directly to PostgreSQL.

When AUDIT_USE_REDIS_STREAM=true:
- POST endpoint publishes the event to Redis Stream.
- Worker consumes from Redis Stream and writes to PostgreSQL.
- Endpoint may return accepted status if async mode is enabled.

Keep the worker simple:
- consumer group
- retry handling
- dead-letter stream for failed events after max attempts
- structured logs

Docker:
Create a Dockerfile for the audit service.

Use uv for dependency install.
Use Python 3.14 base image.
Run as non-root user.
Expose port 8090 inside the Docker network.

docker-compose service names:
- audit-log-service
- audit-postgres
- audit-redis

No load balancer.

Alembic:
Create the initial migration for audit_events.

Testing:
Create tests for:
- live health check
- ready health check
- creating one audit event
- creating a batch of audit events
- auth required on protected endpoints
- invalid token rejected
- idempotency key returns existing event
- search by actor
- search by entity
- entity timeline
- actor timeline
- hash is created
- previous_hash chains correctly
- verify-chain detects valid chain
- verify-chain detects tampering if a stored row is manually changed inside test setup

Code quality:
Add:
- ruff config
- mypy config
- pytest config
- clear README commands

README must include:
- What this service does
- Why it is append-only
- How to run locally
- How to run migrations
- How to run tests
- Example curl requests
- How DFP OS modules should call it
- Why no load balancer is included in this phase
- How to add one later if needed

Integration guidance:
Add a small client helper module that DFP OS can use later.

Suggested file:
services/audit-log/app/client_examples/dfp_audit_client.py

It should show a simple async function:

record_audit_event(
  action,
  entity_type,
  entity_id,
  actor_id,
  before_state,
  after_state,
  metadata
)

This is only an example client. Do not force the main DFP OS app to import from the microservice directly. The service boundary should stay clean.

Acceptance criteria:
The task is complete only when:

1. Audit log microservice runs with Docker Compose.
2. PostgreSQL and Redis run from Docker Compose.
3. No load balancer exists in the compose file.
4. FastAPI service starts successfully.
5. Alembic migration creates the audit_events table.
6. POST /api/v1/audit-events creates an immutable audit event.
7. GET /api/v1/audit-events can search events.
8. Entity timeline endpoint works.
9. Actor timeline endpoint works.
10. Hash chaining works.
11. Verify-chain endpoint works.
12. Protected endpoints require internal bearer token auth.
13. Tests pass.
14. README explains how to run everything.
15. Code is clean, typed, and ready for future DFP OS integration.

Be practical.
Do not overbuild.
Do not add frontend UI in this phase.
Do not add load balancing.
Do not add Kubernetes.
Do not add Kafka.
Do not turn this into a distributed systems science fair.