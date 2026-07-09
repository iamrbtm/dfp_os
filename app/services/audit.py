from __future__ import annotations

from typing import Any

from flask import g, has_request_context, request
from flask_login import current_user

from app.services.audit_client import get_audit_client


def request_metadata(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if has_request_context():
        metadata.update(
            {
                "request_id": getattr(g, "request_id", None),
                "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
                "user_agent": request.headers.get("User-Agent"),
                "path": request.path,
                "method": request.method,
            }
        )
    if extra:
        metadata.update(extra)
    return {k: v for k, v in metadata.items() if v is not None}


def actor_context(
    actor_id: str | int | None = None,
    actor_type: str | None = None,
    actor_display_name: str | None = None,
) -> dict[str, str | None]:
    if actor_id is not None or actor_type is not None or actor_display_name is not None:
        return {
            "actor_id": str(actor_id) if actor_id is not None else None,
            "actor_type": actor_type or "user",
            "actor_display_name": actor_display_name,
        }

    if has_request_context() and current_user and current_user.is_authenticated:
        return {
            "actor_id": str(current_user.id),
            "actor_type": "user",
            "actor_display_name": getattr(current_user, "full_name", None) or getattr(current_user, "email", None),
        }
    if has_request_context() and getattr(g, "api_token", None) is not None:
        token = g.api_token
        return {
            "actor_id": str(token.id),
            "actor_type": "api_token",
            "actor_display_name": token.name,
        }
    return {"actor_id": None, "actor_type": "system", "actor_display_name": "System"}


def record_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    source_module: str | None = None,
    actor_id: str | int | None = None,
    actor_type: str | None = None,
    actor_display_name: str | None = None,
    business_id: str | int | None = None,
    critical: bool = False,
) -> dict[str, Any] | None:
    actor = actor_context(actor_id, actor_type, actor_display_name)
    return get_audit_client().record(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor_id=actor["actor_id"],
        actor_type=actor["actor_type"],
        actor_display_name=actor["actor_display_name"],
        source_module=source_module,
        tenant_id=str(business_id) if business_id is not None else None,
        before_state=before_state,
        after_state=after_state,
        metadata=request_metadata(metadata),
        critical=critical,
    )
