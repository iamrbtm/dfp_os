from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.config import settings


def _stable_json(data: dict[str, Any]) -> str:
    """Deterministic JSON serialization: sorted keys, compact separators."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_fallback)


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _json_fallback(obj: Any) -> str:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return _normalize_dt(obj).isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def build_hash_fields(
    event_id: UUID,
    occurred_at: datetime,
    received_at: datetime,
    tenant_id: str | None,
    actor_id: str | None,
    actor_type: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    source_service: str,
    source_module: str | None,
    request_id: str | None,
    correlation_id: str | None,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    previous_hash: str | None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "occurred_at": occurred_at,
        "received_at": received_at,
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
        "before_state": before_state,
        "after_state": after_state,
        "event_metadata": metadata,
        "previous_hash": previous_hash,
    }


def compute_hash(fields: dict[str, Any]) -> str:
    """Compute HMAC-SHA256 hash of stable JSON-serialized fields."""
    payload = _stable_json(fields)
    return hmac.new(
        settings.hash_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
