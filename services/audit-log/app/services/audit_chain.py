"""Audit chain rebuild — fix a broken hash chain.

The chain is built per-tenant by setting each event's
``previous_hash`` to the hash of the immediately-prior event by
``occurred_at`` and ``received_at``. Sometimes the chain becomes
broken — for example:

* The audit-log microservice was unreachable, the events were
  buffered in Redis and deadmanned to disk, and the deadman was
  replayed with a stale view of the chain.
* Two events were written concurrently and the second writer saw
  the chain state from before the first writer committed.
* A row was edited directly in the database.

This module walks the events in chronological order and rewrites
``previous_hash`` and ``hash`` so the chain is consistent. It is
destructive: existing hashes change. Use it when the chain is
genuinely broken and the audit-log entries themselves are
trusted (the events are real, only the hash linkage is wrong).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.database import async_session_factory
from app.models import AuditEvent
from app.services.hashing import build_hash_fields, compute_hash

logger = logging.getLogger(__name__)


async def rebuild_chain(
    tenant_id: str | None = None,
    *,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Walk every event for ``tenant_id`` (or all events if None) in
    chronological order, recompute ``previous_hash`` and ``hash`` for
    each, and persist the result in batches.

    Returns a summary dict with ``scanned`` (count of events seen),
    ``updated`` (count of events whose hash actually changed),
    ``tenant_id`` (the scope), and ``started_at`` / ``finished_at``
    timestamps. Idempotent: re-running the rebuild on a chain that
    is already correct will report ``updated == 0``.
    """
    from datetime import datetime, timezone

    started_at = datetime.now(timezone.utc)
    scanned = 0
    updated = 0
    previous_hash: str | None = None
    last_received_at = None
    last_occurred_at = None

    while True:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.asc(), AuditEvent.received_at.asc()).limit(batch_size)
        if tenant_id is not None:
            stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
        if last_occurred_at is not None:
            # Subsequent batches: events strictly after the last
            # one's (occurred_at, received_at) pair.
            stmt = stmt.where(
                (AuditEvent.occurred_at > last_occurred_at)
                | ((AuditEvent.occurred_at == last_occurred_at) & (AuditEvent.received_at > last_received_at))
            )

        async with async_session_factory() as session:
            result = await session.execute(stmt)
            events = list(result.scalars().all())
            if not events:
                break

            for event in events:
                fields = build_hash_fields(
                    event_id=event.id,
                    occurred_at=event.occurred_at,
                    received_at=event.received_at,
                    tenant_id=event.tenant_id,
                    actor_id=event.actor_id,
                    actor_type=event.actor_type,
                    action=event.action,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    source_service=event.source_service,
                    source_module=event.source_module,
                    request_id=event.request_id,
                    correlation_id=event.correlation_id,
                    before_state=event.before_state,
                    after_state=event.after_state,
                    metadata=event.event_metadata,
                    previous_hash=previous_hash,
                )
                new_hash = compute_hash(fields)
                if event.previous_hash != previous_hash or event.hash != new_hash:
                    event.previous_hash = previous_hash
                    event.hash = new_hash
                    updated += 1
                previous_hash = new_hash
                last_occurred_at = event.occurred_at
                last_received_at = event.received_at
                scanned += 1
            await session.commit()

    finished_at = datetime.now(timezone.utc)
    logger.info(
        "audit chain rebuild: tenant_id=%s scanned=%d updated=%d duration=%.2fs",
        tenant_id,
        scanned,
        updated,
        (finished_at - started_at).total_seconds(),
    )
    return {
        "tenant_id": tenant_id,
        "scanned": scanned,
        "updated": updated,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
