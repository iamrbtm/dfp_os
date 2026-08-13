"""Tests for the chain-rebuild admin action.

The rebuild walks events in chronological order and rewrites
``previous_hash`` and ``hash`` so the chain is consistent. These
tests cover the case where the chain is broken and the rebuild
fixes it, plus idempotency.
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
async def test_rebuild_chain_fixes_broken_links(client, auth_headers, async_session):
    """Tamper with a hash, then rebuild the chain, then assert the
    timeline reports 'ok' for every link.
    """
    from datetime import datetime, timedelta, timezone

    from app.models import AuditEvent
    from app.services.audit_chain import rebuild_chain

    base = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    e1 = await _post_event(client, auth_headers, action="order.created", occurred_at=base.isoformat())
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at=(base + timedelta(seconds=1)).isoformat(),
        idempotency_key="second",
    )
    await _post_event(
        client,
        auth_headers,
        action="order.shipped",
        occurred_at=(base + timedelta(seconds=2)).isoformat(),
        idempotency_key="third",
    )

    # Tamper: corrupt the second event's hash so the chain is broken.
    from sqlalchemy import select as sa_select

    events = (await async_session.execute(sa_select(AuditEvent).order_by(AuditEvent.occurred_at))).scalars().all()
    events[1].hash = "0" * 64
    events[1].previous_hash = "0" * 64
    await async_session.commit()

    # Sanity: timeline now reports broken.
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    statuses = [e["chain_status"] for e in response.json()]
    assert "broken" in statuses

    # Rebuild.
    result = await rebuild_chain()
    assert result["scanned"] >= 3
    assert result["updated"] >= 1

    # After rebuild: every link is ok.
    response = await client.get(
        "/api/v1/entities/order/order-1/timeline/with-chain",
        headers=auth_headers,
    )
    statuses = [e["chain_status"] for e in response.json()]
    assert statuses[0] == "head"
    assert all(s in ("head", "ok") for s in statuses)


@pytest.mark.asyncio
async def test_rebuild_chain_is_idempotent(client, auth_headers):
    """Re-running the rebuild on a correct chain should report
    updated == 0.
    """
    from app.services.audit_chain import rebuild_chain

    base = "2026-06-15T10:00:00Z"
    await _post_event(client, auth_headers, action="order.created", occurred_at=base)
    await _post_event(
        client,
        auth_headers,
        action="order.updated",
        occurred_at="2026-06-15T10:00:01Z",
        idempotency_key="second",
    )

    first = await rebuild_chain()
    second = await rebuild_chain()
    assert first["scanned"] == second["scanned"]
    # First pass may update 0 (chain is already correct) or
    # may correct 1-2 entries; the second pass should be a no-op.
    assert second["updated"] == 0
