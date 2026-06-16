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
        result = await session.execute(
            select(AuditEvent).where(AuditEvent.id == event_id)
        )
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


async def verify_chain(req: VerifyChainRequest) -> dict[str, Any]:
    """Verify hash chain integrity for the given scope."""
    stmt: Select = (
        select(AuditEvent)
        .order_by(AuditEvent.occurred_at.asc(), AuditEvent.received_at.asc())
    )
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
