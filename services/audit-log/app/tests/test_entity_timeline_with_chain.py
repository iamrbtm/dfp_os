"""Tests for the per-entity timeline-with-chain service.

These exercise the new ``get_entity_timeline_with_chain`` function
and the corresponding ``/entities/.../timeline/with-chain`` HTTP
endpoint. The setup is a fresh in-memory SQLite database per test,
so each scenario can construct exactly the chain shape it needs.
"""

from __future__ import annotations

import pytest


async def _post_event(client, auth_headers, **overrides) -> dict:
    payload = {
        "occurred_at": "2026-06-15T10:00:00Z",
        "actor_id": "user-1",
        "actor_type": "user",
        "action": "test.action",
        "entity_type": "order",
        "entity_id": "order-1",
        "source_service": "test-service",
        "source_module": "test-module",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/audit-events", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def _ts(base: str, offset_seconds: int) -> str:
    """Return an ISO-8601 timestamp ``offset_seconds`` after ``base``."""
    from datetime import datetime, timedelta, timezone

    dt = datetime.fromisoformat(base.replace("Z", "+00:00")) + timedelta(seconds=offset_seconds)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_single_event_is_head(
    client, auth_headers
):
    """A single-event timeline is always 'head', even if previous_hash
    is set (because the global chain is per-tenant, not per-entity).
    """
    await _post_event(client, auth_headers, action="order.created")
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["action"] == "order.created"
    assert events[0]["chain_status"] == "head"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_marks_ok_links(client, auth_headers):
    """Three events with consistent previous_hash values: head, ok, ok.
    Use unique timestamps so the global chain is also adjacent.
    """
    base = "2026-06-15T10:00:00Z"
    await _post_event(client, auth_headers, action="order.created", occurred_at=_ts(base, 0))
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at=_ts(base, 1),
        idempotency_key="second",
    )
    await _post_event(
        client,
        auth_headers,
        action="order.shipped",
        occurred_at=_ts(base, 2),
        idempotency_key="third",
    )
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = response.json()
    # The microservice returns events in ASC order (oldest first) so
    # the timeline reads top-to-bottom in chronological order.
    assert [e["action"] for e in events] == [
        "order.created",
        "order.updated",
        "order.shipped",
    ]
    statuses = [e["chain_status"] for e in events]
    assert statuses[0] == "head"
    # Subsequent events in the same entity should be 'ok' because
    # the global chain is also adjacent.
    assert statuses[1] == "ok"
    assert statuses[2] == "ok"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_ok_when_unrelated_event_sits_between(
    client, auth_headers
):
    """When an unrelated global event sits between two entity events,
    the second entity event's previous_hash points at the unrelated
    event (which exists in the database), so the chain is "ok".
    This is the normal pattern when months of unrelated traffic
    sit between two updates to the same record.
    """
    base = "2026-06-15T10:00:00Z"
    await _post_event(client, auth_headers, action="order.created", occurred_at=_ts(base, 0))
    # Unrelated event in a different entity, in between.
    await _post_event(
        client,
        auth_headers,
        action="customer.created",
        entity_type="customer",
        entity_id="c-1",
        occurred_at=_ts(base, 1),
        idempotency_key="middle",
    )
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at=_ts(base, 2),
        idempotency_key="later",
    )
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    events = response.json()
    assert [e["action"] for e in events] == ["order.created", "order.updated"]
    # First is head, second is ok because the customer.created event
    # in between exists in the database and is what previous_hash
    # actually points to.
    assert events[0]["chain_status"] == "head"
    assert events[1]["chain_status"] == "ok"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_marks_broken_when_previous_event_missing(
    client, auth_headers, async_session
):
    """If we tamper a previous_hash to point at a non-existent event,
    the timeline must flag the link as 'broken'. This is the only
    way the chain can be "broken" from the user's view: a log
    that should be there isn't.
    """
    base = "2026-06-15T10:00:00Z"
    await _post_event(
        client, auth_headers, action="order.created", occurred_at=_ts(base, 0)
    )
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at=_ts(base, 1),
        idempotency_key="second",
    )
    # Tamper: point the second event's previous_hash at a hash that
    # no event in the database has. The chain is now broken because
    # the referenced event is missing.
    from sqlalchemy import select as sa_select

    from app.models import AuditEvent

    events = (
        await async_session.execute(
            sa_select(AuditEvent).order_by(AuditEvent.occurred_at)
        )
    ).scalars().all()
    events[1].previous_hash = "f" * 64  # no event has this hash
    await async_session.commit()

    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    events = response.json()
    # The first event is still head; the second event's previous_hash
    # points at nothing in the database, so chain_status is "broken".
    assert events[0]["chain_status"] == "head"
    assert events[1]["chain_status"] == "broken"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_excludes_other_entities(
    client, auth_headers
):
    """Events for a different entity_type/entity_id should not appear
    in this entity's timeline.
    """
    base = "2026-06-15T10:00:00Z"
    await _post_event(client, auth_headers, action="order.created", occurred_at=_ts(base, 0))
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at=_ts(base, 1),
        idempotency_key="same-order",
    )
    # Different order, same type.
    await _post_event(
        client,
        auth_headers,
        action="order.created",
        entity_id="order-2",
        occurred_at=_ts(base, 2),
        idempotency_key="other-order",
    )
    # Different entity_type.
    await _post_event(
        client,
        auth_headers,
        action="customer.created",
        entity_type="customer",
        entity_id="cust-1",
        occurred_at=_ts(base, 3),
        idempotency_key="customer",
    )

    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    events = response.json()
    assert {e["action"] for e in events} == {"order.created", "order.updated"}
    assert all(e["entity_id"] == "order-1" for e in events)


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_respects_limit(client, auth_headers):
    """The default limit is 200; explicit limit is honoured."""
    base = "2026-06-15T10:00:00Z"
    for i in range(5):
        await _post_event(
            client,
            auth_headers,
            action=f"order.step_{i}",
            occurred_at=_ts(base, i),
            idempotency_key=f"step-{i}",
        )
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain?limit=3",
        headers=auth_headers,
    )
    events = response.json()
    assert len(events) == 3
