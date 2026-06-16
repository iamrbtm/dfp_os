from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    idempotency_key: str | None = None
    tenant_id: str | None = None
    occurred_at: datetime
    actor_id: str | None = None
    actor_type: str | None = None
    actor_display_name: str | None = None
    action: str = Field(..., min_length=1, max_length=120)
    entity_type: str = Field(..., min_length=1, max_length=120)
    entity_id: str | None = None
    source_service: str = Field(..., min_length=1, max_length=120)
    source_module: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AuditEventCreateResponse(BaseModel):
    id: str
    received_at: datetime
    hash: str
    previous_hash: str | None


class AuditEventBatchCreate(BaseModel):
    events: list[AuditEventCreate] = Field(..., max_length=100)


class AuditEventBatchResponse(BaseModel):
    created: list[AuditEventCreateResponse]
    total: int


class AuditEventSearchParams(BaseModel):
    tenant_id: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    source_service: str | None = None
    source_module: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditEventResponse(BaseModel):
    id: str
    idempotency_key: str | None
    tenant_id: str | None
    occurred_at: datetime
    received_at: datetime
    actor_id: str | None
    actor_type: str | None
    actor_display_name: str | None
    action: str
    entity_type: str
    entity_id: str | None
    source_service: str
    source_module: str | None
    request_id: str | None
    correlation_id: str | None
    ip_address: str | None
    user_agent: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    metadata: dict[str, Any] | None
    hash: str
    previous_hash: str | None


class VerifyChainRequest(BaseModel):
    tenant_id: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


class VerifyChainResponse(BaseModel):
    valid: bool
    checked_count: int
    first_invalid_event_id: str | None
