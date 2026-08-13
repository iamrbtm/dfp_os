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
    """Three events with consistent previous_hash values: head, ok, ok."""
    await _post_event(client, auth_headers, action="order.created")
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        idempotency_key="second",
    )
    await _post_event(
        client,
        auth_headers,
        action="order.shipped",
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
    # the writer threads previous_hash from the prior entity event.
    assert statuses[1] == "ok"
    assert statuses[2] == "ok"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_marks_broken_link(client, auth_headers, async_session):
    """If we tamper with a stored hash to break the chain, the timeline
    must flag the broken event as 'broken'.
    """
    first = await _post_event(client, auth_headers, action="order.created")
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        idempotency_key="second",
    )
    # Tamper: corrupt the first event's hash so the second's
    # previous_hash no longer matches.
    from app.models import AuditEvent

    first_event = await async_session.get(AuditEvent, first["id"])
    first_event.hash = "0" * 64
    await async_session.commit()

    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    events = response.json()
    # The first event still has chain_status='head' (it's the first
    # in the entity). The second event must be flagged 'broken'.
    assert events[0]["chain_status"] == "head"
    assert events[1]["chain_status"] == "broken"


@pytest.mark.asyncio
async def test_entity_timeline_with_chain_excludes_other_entities(
    client, auth_headers
):
    """Events for a different entity_type/entity_id should not appear
    in this entity's timeline.
    """
    await _post_event(client, auth_headers, action="order.created")
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        idempotency_key="same-order",
    )
    # Different order, same type.
    await _post_event(
        client,
        auth_headers,
        action="order.created",
        entity_id="order-2",
        idempotency_key="other-order",
    )
    # Different entity_type.
    await _post_event(
        client,
        auth_headers,
        action="customer.created",
        entity_type="customer",
        entity_id="cust-1",
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
    for i in range(5):
        await _post_event(
            client,
            auth_headers,
            action=f"order.step_{i}",
            idempotency_key=f"step-{i}",
        )
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain?limit=3",
        headers=auth_headers,
    )
    events = response.json()
    assert len(events) == 3
