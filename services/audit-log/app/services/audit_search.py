from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, desc, select

from app.database import async_session_factory
from app.models import AuditEvent
from app.schemas import VerifyChainRequest
from app.services.hashing import build_hash_fields, compute_hash


async def search_audit_events(
    *,
    tenant_id: str | None = None,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    source_service: str | None = None,
    source_module: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt: Select = (
        select(AuditEvent)
        .order_by(desc(AuditEvent.occurred_at), desc(AuditEvent.received_at))
        .limit(limit)
        .offset(offset)
    )

    filters = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_service": source_service,
        "source_module": source_module,
        "request_id": request_id,
        "correlation_id": correlation_id,
    }
    for attr, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(AuditEvent, attr) == value)

    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= occurred_to)

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_audit_event_by_id(event_id: str) -> AuditEvent | None:
    async with async_session_factory() as session:
        result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        return result.scalar_one_or_none()


async def get_entity_timeline(
    entity_type: str,
    entity_id: str,
    tenant_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt: Select = (
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(desc(AuditEvent.occurred_at), desc(AuditEvent.received_at))
        .limit(limit)
        .offset(offset)
    )
    if tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= occurred_to)

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_actor_timeline(
    actor_id: str,
    tenant_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    stmt: Select = (
        select(AuditEvent)
        .where(AuditEvent.actor_id == actor_id)
        .order_by(desc(AuditEvent.occurred_at), desc(AuditEvent.received_at))
        .limit(limit)
        .offset(offset)
    )
    if tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= occurred_to)

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_entity_timeline_with_chain(
    entity_type: str,
    entity_id: str,
    tenant_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return every event for an entity, oldest first, annotated with
    ``chain_status`` so the UI can highlight broken links.

    The chain is global (per tenant) and links every event to the
    immediately-prior event by ``occurred_at``. From the entity's
    perspective, two adjacent entity events may have unrelated
    global events (other orders, other users) between them — that's
    normal traffic, not a problem.

    ``chain_status`` is one of:

      * ``"head"`` — the first event in this entity's timeline.
      * ``"ok"`` — this event's ``previous_hash`` points at an event
        that actually exists in the database. The "previous" event
        may not be the prior event in the entity's view (it may be
        any unrelated global event between this one and the prior
        entity event); that's normal. The chain is only "ok" if the
        referenced event is present.
      * ``"broken"`` — the chain is broken. Either
        ``previous_hash`` is null mid-chain, or it does not match
        any event in the database. The UI surfaces both expected
        and actual hashes so an operator can see what is missing.
        This fires when a log was never recorded or was deleted
        out from under the chain. The chain-rebuild admin action
        fixes these.

    Events are returned in ascending ``occurred_at`` order (oldest
    first) so the timeline reads top-to-bottom in chronological
    order. Use ``offset`` to skip the first N events for pagination.
    """
    from sqlalchemy import select as sa_select

    from app.models import AuditEvent

    stmt: Select = (
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.received_at.asc())
        .limit(limit)
        .offset(offset)
    )
    if tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= occurred_to)

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        events = list(result.scalars().all())

        if not events:
            return []

        # For each event in the entity timeline, check whether the
        # event referenced by ``previous_hash`` actually exists in
        # the database. The chain is "ok" if and only if every
        # previous_hash points at a real event — even if the
        # referenced event is from a different entity (e.g. a user
        # login) or hundreds of events apart in occurred_at. The
        # chain is "broken" only if the referenced event does not
        # exist (was never recorded, or was deleted) or if
        # previous_hash is null mid-chain.
        #
        # We do this in a single query: SELECT id FROM audit_events
        # WHERE hash IN (...event.previous_hash values...).
        previous_hash_values = [e.previous_hash for e in events if e.previous_hash]
        existing_hashes: set[str] = set()
        if previous_hash_values:
            existing_q = sa_select(AuditEvent.hash).where(AuditEvent.hash.in_(previous_hash_values))
            if tenant_id is not None:
                existing_q = existing_q.where(AuditEvent.tenant_id == tenant_id)
            rows = (await session.execute(existing_q)).scalars().all()
            existing_hashes = set(rows)

    annotated: list[dict[str, Any]] = []
    for i, event in enumerate(events):
        event_dict = _event_to_dict(event)
        event_dict["chain_status"] = _classify_chain_status(
            event=event,
            prior_in_entity=events[i - 1] if i > 0 else None,
            previous_event_exists=(event.previous_hash in existing_hashes if event.previous_hash else False),
        )
        annotated.append(event_dict)
    return annotated


def _classify_chain_status(
    *,
    event,
    prior_in_entity,
    previous_event_exists: bool,
) -> str:
    """Decide the chain_status for one event.

    Three outcomes:

      * ``"head"`` — first event in this entity's timeline.
      * ``"ok"`` — this event's ``previous_hash`` points at an event
        that exists in the database. The previous event may not be
        the prior entity event (it may be any unrelated global
        event between this one and the prior entity event); that's
        normal traffic and the chain is still intact. This is the
        rule that fixes the entity-#36 false-positive: the events
        in that entity's timeline are far apart in the global
        chain, but the prior events do exist somewhere, so the chain
        is "ok".
      * ``"broken"`` — the chain is broken. Either
        ``previous_hash`` is null mid-chain, or it does not match
        any event in the database. This is the rule that catches a
        real integrity issue: a log that was never recorded, or one
        that was deleted out from under the chain. The chain-rebuild
        admin action fixes these.
    """
    if prior_in_entity is None:
        return "head"

    if event.previous_hash is None:
        return "broken"

    if not previous_event_exists:
        return "broken"

    return "ok"


def _event_to_dict(event: AuditEvent) -> dict[str, Any]:
    """Serialize an AuditEvent ORM instance to the JSON shape the
    Flask app and the API schema both speak.
    """
    return {
        "id": str(event.id),
        "idempotency_key": event.idempotency_key,
        "tenant_id": event.tenant_id,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "actor_display_name": event.actor_display_name,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "source_service": event.source_service,
        "source_module": event.source_module,
        "request_id": event.request_id,
        "correlation_id": event.correlation_id,
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "before_state": event.before_state or {},
        "after_state": event.after_state or {},
        "metadata": event.event_metadata,
        "hash": event.hash,
        "previous_hash": event.previous_hash,
    }


async def verify_chain(req: VerifyChainRequest) -> dict[str, Any]:
    """Verify hash chain integrity for the given scope."""
    stmt: Select = select(AuditEvent).order_by(AuditEvent.occurred_at.asc(), AuditEvent.received_at.asc())
    if req.tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == req.tenant_id)
    if req.occurred_from is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= req.occurred_from)
    if req.occurred_to is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= req.occurred_to)

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        events = list(result.scalars().all())

    if not events:
        return {"valid": True, "checked_count": 0, "first_invalid_event_id": None}

    for i, event in enumerate(events):
        prev_hash = events[i - 1].hash if i > 0 else None
        if event.previous_hash != prev_hash:
            return {
                "valid": False,
                "checked_count": i + 1,
                "first_invalid_event_id": str(event.id),
            }

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
            previous_hash=event.previous_hash,
        )
        expected = compute_hash(fields)
        if event.hash != expected:
            return {
                "valid": False,
                "checked_count": i + 1,
                "first_invalid_event_id": str(event.id),
            }

    return {"valid": True, "checked_count": len(events), "first_invalid_event_id": None}
