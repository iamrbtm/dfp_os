from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.schemas import (
    AuditEventBatchCreate,
    AuditEventBatchResponse,
    AuditEventCreate,
    AuditEventCreateResponse,
    AuditEventResponse,
    AuditEventSearchParams,
    VerifyChainRequest,
    VerifyChainResponse,
)
from app.security import verify_internal_token
from app.services.audit_search import (
    get_actor_timeline,
    get_audit_event_by_id,
    get_entity_timeline,
    search_audit_events,
    verify_chain,
)
from app.services.audit_writer import create_audit_event
from app.services.redis_streams import publish_to_stream

router = APIRouter(prefix="/api/v1", tags=["audit-events"], dependencies=[Depends(verify_internal_token)])


def _event_to_response(event) -> AuditEventResponse:
    return AuditEventResponse(
        id=str(event.id),
        idempotency_key=event.idempotency_key,
        tenant_id=event.tenant_id,
        occurred_at=event.occurred_at,
        received_at=event.received_at,
        actor_id=event.actor_id,
        actor_type=event.actor_type,
        actor_display_name=event.actor_display_name,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source_service=event.source_service,
        source_module=event.source_module,
        request_id=event.request_id,
        correlation_id=event.correlation_id,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        before_state=event.before_state,
        after_state=event.after_state,
        metadata=event.event_metadata,
        hash=event.hash,
        previous_hash=event.previous_hash,
    )


def _create_to_response(event) -> AuditEventCreateResponse:
    return AuditEventCreateResponse(
        id=str(event.id),
        received_at=event.received_at,
        hash=event.hash,
        previous_hash=event.previous_hash,
    )


@router.post("/audit-events", status_code=status.HTTP_201_CREATED)
async def post_audit_event(body: AuditEventCreate) -> AuditEventCreateResponse:
    total_bytes = len(body.model_dump_json(exclude={"before_state", "after_state", "metadata"}))
    for field in ("before_state", "after_state", "metadata"):
        val = getattr(body, field)
        if val is not None:
            import json
            total_bytes += len(json.dumps(val))
    if total_bytes > 1_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "payload_too_large", "message": "Total payload exceeds 1MB limit."},
        )

    if settings.use_redis_stream:
        msg_id = await publish_to_stream(body.model_dump(mode="json"))
        return AuditEventCreateResponse(
            id=msg_id,
            received_at=datetime.now(timezone.utc),
            hash="pending",
            previous_hash=None,
        )

    event = await create_audit_event(
        idempotency_key=body.idempotency_key,
        tenant_id=body.tenant_id,
        occurred_at=body.occurred_at,
        actor_id=body.actor_id,
        actor_type=body.actor_type,
        actor_display_name=body.actor_display_name,
        action=body.action,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        source_service=body.source_service,
        source_module=body.source_module,
        request_id=body.request_id,
        correlation_id=body.correlation_id,
        ip_address=body.ip_address,
        user_agent=body.user_agent,
        before_state=body.before_state,
        after_state=body.after_state,
        metadata=body.metadata,
    )
    return _create_to_response(event)


@router.post("/audit-events/batch", status_code=status.HTTP_201_CREATED)
async def post_audit_events_batch(body: AuditEventBatchCreate) -> AuditEventBatchResponse:
    created: list[AuditEventCreateResponse] = []
    for evt in body.events:
        event = await create_audit_event(
            idempotency_key=evt.idempotency_key,
            tenant_id=evt.tenant_id,
            occurred_at=evt.occurred_at,
            actor_id=evt.actor_id,
            actor_type=evt.actor_type,
            actor_display_name=evt.actor_display_name,
            action=evt.action,
            entity_type=evt.entity_type,
            entity_id=evt.entity_id,
            source_service=evt.source_service,
            source_module=evt.source_module,
            request_id=evt.request_id,
            correlation_id=evt.correlation_id,
            ip_address=evt.ip_address,
            user_agent=evt.user_agent,
            before_state=evt.before_state,
            after_state=evt.after_state,
            metadata=evt.metadata,
        )
        created.append(_create_to_response(event))
    return AuditEventBatchResponse(created=created, total=len(created))


@router.get("/audit-events")
async def get_audit_events(
    tenant_id: str | None = Query(None),
    actor_id: str | None = Query(None),
    actor_type: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    source_service: str | None = Query(None),
    source_module: str | None = Query(None),
    request_id: str | None = Query(None),
    correlation_id: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditEventResponse]:
    params = AuditEventSearchParams(
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
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    events = await search_audit_events(**params.model_dump(exclude_none=True))
    return [_event_to_response(e) for e in events]


@router.get("/audit-events/{event_id}")
async def get_audit_event(event_id: str) -> AuditEventResponse:
    event = await get_audit_event_by_id(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Audit event not found."},
        )
    return _event_to_response(event)


@router.get("/entities/{entity_type}/{entity_id}/timeline")
async def entity_timeline(
    entity_type: str,
    entity_id: str,
    tenant_id: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditEventResponse]:
    events = await get_entity_timeline(
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return [_event_to_response(e) for e in events]


@router.get("/actors/{actor_id}/timeline")
async def actor_timeline(
    actor_id: str,
    tenant_id: str | None = Query(None),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[AuditEventResponse]:
    events = await get_actor_timeline(
        actor_id=actor_id,
        tenant_id=tenant_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return [_event_to_response(e) for e in events]


@router.post("/audit-events/verify-chain")
async def verify_chain_endpoint(body: VerifyChainRequest) -> VerifyChainResponse:
    result = await verify_chain(body)
    return VerifyChainResponse(
        valid=result["valid"],
        checked_count=result["checked_count"],
        first_invalid_event_id=result["first_invalid_event_id"],
    )
