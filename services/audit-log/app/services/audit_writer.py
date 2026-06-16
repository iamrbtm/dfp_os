from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text

from app.database import async_session_factory, engine
from app.models import AuditEvent
from app.services.hashing import build_hash_fields, compute_hash


async def get_previous_hash(session, tenant_id: str | None) -> str | None:
    """Get the most recent audit event hash for chaining."""
    stmt = (
        select(AuditEvent.hash)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.received_at.desc())
        .limit(1)
    )
    if tenant_id:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def create_audit_event(
    *,
    idempotency_key: str | None = None,
    tenant_id: str | None = None,
    occurred_at: datetime | None = None,
    actor_id: str | None = None,
    actor_type: str | None = None,
    actor_display_name: str | None = None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    source_service: str,
    source_module: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a new audit event with hash chaining.

    Uses a transaction-level advisory lock to prevent race conditions
    on the hash chain for the same tenant.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    occurred = occurred_at or now

    async with async_session_factory() as session:
        async with session.begin():
            is_postgres = engine.dialect.name == "postgresql"
            if is_postgres:
                if tenant_id:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                        {"key": f"audit_chain_{tenant_id}"},
                    )
                else:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext('audit_chain_global'))"),
                    )

            if idempotency_key:
                existing = await session.execute(
                    select(AuditEvent).where(AuditEvent.idempotency_key == idempotency_key)
                )
                existing_event = existing.scalar_one_or_none()
                if existing_event is not None:
                    return existing_event

            previous_hash = await get_previous_hash(session, tenant_id)

            hash_fields = build_hash_fields(
                event_id=event_id,
                occurred_at=occurred,
                received_at=now,
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type=actor_type,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                source_service=source_service,
                source_module=source_module,
                request_id=request_id,
                correlation_id=correlation_id,
                before_state=before_state,
                after_state=after_state,
                metadata=metadata,
                previous_hash=previous_hash,
            )
            event_hash = compute_hash(hash_fields)

            event = AuditEvent(
                id=event_id,
                idempotency_key=idempotency_key,
                tenant_id=tenant_id,
                occurred_at=occurred,
                received_at=now,
                actor_id=actor_id,
                actor_type=actor_type,
                actor_display_name=actor_display_name,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                source_service=source_service,
                source_module=source_module,
                request_id=request_id,
                correlation_id=correlation_id,
                ip_address=ip_address,
                user_agent=user_agent,
                before_state=before_state,
                after_state=after_state,
                metadata=metadata,
                hash=event_hash,
                previous_hash=previous_hash,
            )
            session.add(event)

        return event
