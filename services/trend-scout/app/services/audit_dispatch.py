"""Audit dispatch helper for the Trend Scout microservice.

Forwards audit events through the existing audit-log microservice via
``app.services.audit_client`` (re-exported as a convenience so callers can
``from app.services.audit_dispatch import dispatch_audit_event`` regardless of
whether the integration is direct or proxied).

The Phase 2 implementation is a thin async wrapper that swallows network
errors (we never want audit dispatch to break the pipeline). Phase 4 will
add Redis-stream buffering for retry.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def dispatch_audit_event(
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: str | None = None,
    actor_type: str = "system",
    actor_display_name: str = "trend-scout",
    source_module: str = "app.services.audit_dispatch",
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    business_id: int | None = None,
) -> bool:
    """Dispatch an audit event to the audit-log microservice.

    Returns True if the event was acknowledged, False on any failure. Never
    raises — audit dispatch is best-effort during Phase 2. Critical financial
    actions will switch to fail-closed in later phases.
    """
    try:
        import httpx

        from app.config import settings

        if not settings.audit_log_enabled:
            logger.debug("Audit dispatch skipped (audit_log_enabled=false): %s", action)
            return False

        url = f"{settings.audit_log_base_url.rstrip('/')}/api/v1/audit-events"
        headers = {
            "Authorization": f"Bearer {settings.audit_log_token}",
            "Accept": "application/json",
        }
        payload = {
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "actor_id": actor_id,
            "actor_type": actor_type,
            "actor_display_name": actor_display_name,
            "source_module": source_module,
            "before_state": before_state,
            "after_state": after_state,
            "metadata": metadata or {},
            "business_id": business_id,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning("Audit dispatch non-2xx for %s: HTTP %s", action, resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("Audit dispatch failed for %s: %s", action, exc)
        return False
