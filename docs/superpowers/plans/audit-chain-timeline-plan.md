# Plan: Audit Event Detail — Chain Timeline View

**Generated**: 2026-08-13
**Estimated Complexity**: Medium

## Overview

The audit detail page (`/audit-logs/<event_id>`) currently shows the
fields of one event but gives no sense of where it sits in the broader
history. The user wants a **vertical timeline of the entire record's
history** at the bottom of the detail page: creation → … → current
event → any later events for the same record. The user wants to be
able to click any dot in the timeline and jump to that event's detail.

There are two complementary sources of truth in the audit-log
microservice:

1. **Entity timeline** (`GET /api/v1/entities/<type>/<id>/timeline`)
   — every event for a given `entity_type` + `entity_id`, ordered by
   `occurred_at desc`. This is the *narrative* — what happened to this
   record.
2. **Hash chain** — `previous_hash → hash` linkage per tenant.
   This is the *integrity layer* — proves nothing was tampered with.

The plan below combines them: the timeline UI is built from the entity
timeline, and a small per-event "chain integrity" badge tells the user
whether the event's `previous_hash` matches the hash of the event
immediately before it in the timeline.

Per the user's clarification:
- **Scope**: per-record (entity_type + entity_id), tenant-scoped.
- **Navigation**: full chain loaded eagerly (one round trip, scrollable).
- **Broken chain**: render with a red "BROKEN CHAIN" marker, don't hide.
- **Filtering**: toggle between "this record only" (default) and
  "all events for this entity_type" in the timeline view.
- **Visual**: vertical timeline with a connecting line and dots;
  current event highlighted; clicking a dot jumps to that event.

## Prerequisites

- `services/audit-log/` running with Alembic migrations applied
  (`audit_events` table populated, see `docs/audit_log.md`).
- Existing `AuditClient` in `app/services/audit_client.py` with
  `search()` and `get()` methods.
- The user's chosen UX (vertical timeline, full chain loaded eagerly).

## Sprint 1: API + Service Layer

**Goal**: Add the server-side capability to fetch a full per-record
timeline with chain-integrity annotations, so the detail page can
display it in one round trip.

**Demo/Validation**:
- `curl -H "Authorization: Bearer $TOK" "http://audit-log:8090/api/v1/entities/order/123/timeline"` returns every event for `order#123`, in order, with each event annotated with `chain_status: "ok" | "broken" | "head"`.
- `curl -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d '{"entity_type":"order","entity_id":"123"}' http://audit-log:8090/api/v1/audit-events/verify-chain` returns the same chain verdict.

### Task 1.1: Add `entity_timeline_with_chain` service

- **Location**: `services/audit-log/app/services/audit_search.py`
- **Description**: Add a new async function `get_entity_timeline_with_chain(entity_type, entity_id, tenant_id=None)` that:
  1. Calls `get_entity_timeline(...)` to get the events, ordered by `occurred_at` ASC for chronological walk (note: the existing `get_entity_timeline` returns DESC — the new function must reverse, or expose its own ASC query).
  2. For each event, computes `chain_status`:
     - `"head"` if `previous_hash is None`
     - `"ok"` if `previous_hash == previous event's hash`
     - `"broken"` if mismatch
  3. Returns a list of dicts combining the event payload with `chain_status`.
- **Dependencies**: existing `get_entity_timeline`.
- **Acceptance Criteria**:
  - Function returns events in ASC order (oldest first).
  - Each event has `chain_status` correctly computed.
  - First event in the chain has `chain_status == "head"` unless its `previous_hash` matches a non-existent predecessor (in which case it's broken).
  - Single SQL query, no N+1.
- **Validation**: pytest in `services/audit-log/app/tests/`:
  - `test_entity_timeline_with_chain_returns_ordered_events`
  - `test_entity_timeline_with_chain_marks_head`
  - `test_entity_timeline_with_chain_detects_broken_link`

### Task 1.2: Add `/entities/{type}/{id}/timeline/with-chain` endpoint

- **Location**: `services/audit-log/app/api/routes/audit_events.py`
- **Description**: Add a thin FastAPI route that wraps the new service function, returning `list[AuditEventWithChainStatus]`. Add the response schema to `services/audit-log/app/schemas/__init__.py` (extend `AuditEventResponse` with an optional `chain_status: str | None` field, or define a new `AuditEventWithChainStatus(AuditEventResponse)` model).
- **Dependencies**: Task 1.1.
- **Acceptance Criteria**:
  - Endpoint requires bearer token (already enforced by `verify_internal_token`).
  - Same query params as `/timeline`: `tenant_id`, `occurred_from`, `occurred_to`, `limit`, `offset`.
  - Returns 200 with the annotated list.
- **Validation**: pytest in `services/audit-log/app/tests/`:
  - `test_entities_timeline_with_chain_endpoint`

### Task 1.3: Add `entity_timeline_with_chain` to the AuditClient

- **Location**: `app/services/audit_client.py`
- **Description**: Add `AuditClient.entity_timeline(entity_type, entity_id, ...)` that calls the new endpoint. Returns a list of event dicts, each with an extra `chain_status` field.
- **Dependencies**: Task 1.2.
- **Acceptance Criteria**:
  - Method is available without monkey-patching.
  - Honors `AUDIT_LOG_ENABLED` (returns `[]` if disabled).
  - Returns `None` on network error and logs a warning (consistent with `search`/`get`).
- **Validation**: add to `tests/test_audit_outbox.py` (or a new `tests/test_audit_client_timeline.py`):
  - `test_audit_client_entity_timeline_returns_annotated_events` (uses `httpx.MockTransport`).

## Sprint 2: Flask Route + Template

**Goal**: Surface the chain-annotated timeline at the bottom of the
detail page. Current event highlighted, broken links marked, entity
toggle works, clicking a dot jumps to that event.

**Demo/Validation**:
- Log in as admin, visit `/audit-logs/`, click any event.
- Scroll to the bottom: see a vertical timeline with the current event highlighted in a different colour.
- Click an older dot → URL changes to `/audit-logs/<that-id>`, page loads with that event now highlighted.
- Click an older dot whose `previous_hash` is broken → see a red "BROKEN CHAIN" marker between the two events, with the expected vs actual hash shown.
- Toggle "this record only" / "all events for this entity_type" and watch the timeline change without a page reload (HTMX).

### Task 2.1: Extend `detail` view to fetch the chain

- **Location**: `app/blueprints/audit_logs/routes.py`
- **Description**: After fetching the event, also fetch `client.entity_timeline(event["entity_type"], event["entity_id"], tenant_id=event.get("tenant_id"))`. Pass both to the template. Handle the case where `entity_type` or `entity_id` is missing (timeline is empty).
- **Dependencies**: Sprint 1.
- **Acceptance Criteria**:
  - 404 still works (event not found).
  - Timeline is fetched in the same request (no client-side async fetch in v1).
  - Empty `entity_type` / `entity_id` → empty timeline, no error.
- **Validation**: extend `tests/test_phase4_ux.py` (or add `tests/test_audit_logs_detail.py`):
  - `test_audit_logs_detail_renders_timeline`
  - `test_audit_logs_detail_handles_event_without_entity`

### Task 2.2: Add `?scope=record|type` query param and toggle

- **Location**: `app/blueprints/audit_logs/routes.py`
- **Description**: When `?scope=type` is set, fetch every event for the same `entity_type` (all orders, all products, etc.). Default `scope=record` shows only this record's events. Pass the active scope to the template.
- **Dependencies**: Task 2.1.
- **Acceptance Criteria**:
  - Default is `record` and the URL has no `?scope=` param.
  - `?scope=type` shows broader events.
  - The toggle in the template preserves other query params (so filters from the index page still apply).
- **Validation**: `test_audit_logs_detail_with_scope_type`.

### Task 2.3: Build the vertical-timeline partial

- **Location**: `app/templates/audit_logs/_timeline.html` (new partial), included by `detail.html`.
- **Description**: A vertical list of events, oldest at top. Each event is a row with:
  - A connector line on the left (vertical line + dot)
  - Timestamp, action, actor, entity reference
  - A chain-status badge: green check (ok), red "BROKEN" (mismatch), grey "FIRST" (head)
  - For the current event: highlighted background, "current" label
  - Each row is a link to that event's detail page
- **Design tokens**: use `var(--color-card)`, `var(--color-link)`, `var(--color-warning-bg)` for the broken marker (per AGENTS.md "Do not hardcode colors").
- **HTMX** (`hx-get`, `hx-target`, `hx-swap="outerHTML"`): on toggle change, swap the timeline partial with the new scope. The Flask route returns the partial on `HX-Request: true`.
- **Dependencies**: Task 2.2.
- **Acceptance Criteria**:
  - Partial renders standalone (no `extends`).
  - Visual style matches the rest of the audit module (same card style, fonts, spacing).
  - Broken-chain marker shows both expected and actual hash so an operator can decide what changed.
  - Current event is visually distinguished.
  - HTMX toggle works without full-page reload.
- **Validation**: snapshot test via Playwright or visual diff (manual until Playwright is wired into CI for this module).

### Task 2.4: Update `detail.html` to render the partial

- **Location**: `app/templates/audit_logs/detail.html`
- **Description**: Below the existing "Integrity chain" card, render `{% include "audit_logs/_timeline.html" %}`. Pass the events and the current event id as context.
- **Dependencies**: Task 2.3.
- **Acceptance Criteria**:
  - Timeline appears below the integrity-chain card, not above.
  - Empty timeline (entityless events) shows a friendly message: "This event has no entity to show a timeline for."
  - Toggle is rendered above the timeline when `entity_type` is set.
- **Validation**: same as Task 2.3.

### Task 2.5: Update the index page to link cleanly into the timeline

- **Location**: `app/templates/audit_logs/index.html`
- **Description**: No UI change — the row click already navigates to detail. Add a small "View record history" hint near the entity cell when the event has an `entity_id`, so users discover the feature.
- **Dependencies**: Sprint 2 done.
- **Acceptance Criteria**:
  - The entity cell shows "order#123 →" with the arrow as a subtle affordance.
  - The arrow is the link to the detail page; nothing new is added to the row's primary click handler.

## Sprint 3: Tests + Docs

**Goal**: Lock in behaviour and update the operational docs.

**Demo/Validation**:
- `pytest` shows new tests passing alongside the existing 17 audit tests.
- `docs/audit_log.md` documents the timeline view, how to read it, and what the "BROKEN CHAIN" badge means.

### Task 3.1: Add unit tests for the chain-status computation

- **Location**: `services/audit-log/app/tests/test_chain_status.py` (new file)
- **Description**: Three test cases — all events with consistent hashes, a broken link in the middle, a head event. Each inserts a known sequence of events and asserts the `chain_status` field on each.
- **Dependencies**: Sprint 1.
- **Acceptance Criteria**: 3 tests, all pass.

### Task 3.2: Add Flask-level integration test

- **Location**: `tests/test_audit_logs_detail.py` (new file)
- **Description**: Login as admin, GET `/audit-logs/<id>` with a stubbed AuditClient that returns a known event + timeline. Assert the response contains the timeline partial, the current event is marked, and the toggle link works.
- **Dependencies**: Sprint 2.
- **Acceptance Criteria**: 2-3 tests, all pass.

### Task 3.3: Update `docs/audit_log.md`

- **Location**: `docs/audit_log.md`
- **Description**: Add a "Browsing the audit log" section explaining:
  - How to read the detail page
  - The vertical timeline at the bottom
  - The "record" vs "entity_type" scope toggle
  - What "BROKEN CHAIN" means and what to do about it
  - A pointer to `verify-chain` for full verification
- **Dependencies**: Sprint 2.
- **Acceptance Criteria**: Docs render correctly, the section is linked from the audit_logs index page.

## Sprint 4: Verify + Push

- Manual smoke test on the live system:
  - Trigger an event for a known entity, navigate to its detail page, see the timeline.
  - Pick an old event from a long chain, navigate to it, see "you are here" in the timeline.
  - Simulate a broken chain by editing one event's `hash` in the DB, refresh, see the red marker.
- Run `uv run ruff check .` and `uv run ruff format --check .`
- Run targeted tests
- Push the commits; rebuild web container; verify the page works end-to-end against the live audit-log microservice.

## Testing Strategy

| Layer | Tool | Coverage |
|---|---|---|
| Service unit (chain status) | `pytest` | All chain-status branches |
| API endpoint | `pytest` + httpx | Status codes, response shape, auth |
| AuditClient method | `pytest` + httpx MockTransport | Network failure path |
| Flask route | `pytest` + Flask test_client | Timeline fetched and passed |
| Template rendering | `pytest` + `assertTemplateUsed` | Timeline partial included |
| End-to-end (manual) | browser | Full UX, broken-link marker, toggle |

## Potential Risks & Gotchas

1. **Hash chain is per-tenant.** Single-tenant DFPos means tenant is null. `get_entity_timeline_with_chain` must accept `tenant_id=None` and handle it. The endpoint `?tenant_id=` query param should be honored but default to the event's `tenant_id` (or None for the default tenant).
2. **Timeline size.** A record with thousands of events will be huge. The existing `limit=500` cap protects the microservice; the Flask side should also cap and paginate. v1: use `limit=200` and show "Showing 200 of N" with a "load more" link if N > 200.
3. **Events without entity_type / entity_id.** Some events (e.g. `module.disabled_access_attempted` from the global hook) have no entity. The timeline must degrade gracefully.
4. **Ordering ambiguity.** Two events with the same `occurred_at` (microsecond-resolution collisions in load tests) need a stable secondary sort. Use `(occurred_at ASC, received_at ASC)` — already the convention in `verify_chain`.
5. **HTMX edge case.** The HTMX toggle changes the URL but the user's filters on the index page should be preserved when navigating. Make sure the timeline links round-trip the filter query params.
6. **The existing `entity_timeline` returns DESC.** Don't reuse it directly — call `select(...).order_by(occurred_at.asc(), received_at.asc())` instead.
7. **Don't trust the client to compute chain_status.** Server-side computation is the source of truth. The Flask side only renders what the microservice returns.
8. **Cross-tenant leakage.** `entity_type` + `entity_id` may collide across tenants. Always include `tenant_id` in the filter for the microservice query; default it to `None` only if the event itself has `tenant_id=None`.

## Rollback Plan

- Each task is committable independently.
- If the new timeline endpoint breaks the microservice, revert the route registration and the service function; the rest of the audit API is untouched.
- If the partial breaks the detail page, the worst case is a 500 — revert the `{% include %}` in `detail.html` (single commit) to restore the previous layout.
