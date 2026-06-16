"""Example client for DFP OS modules to call the audit log microservice.

This is a reference implementation. It lives inside the microservice boundary
to document the expected contract. DFP OS should implement its own call in
whichever way fits (sync httpx, async httpx, background task, etc.).

Usage (inside DFP OS):
  from httpx import Client
  client = Client(base_url="http://audit-log-service:8090")
  client.post("/api/v1/audit-events", json={...}, headers={"Authorization": "Bearer <token>"})
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


class DfpAuditClient:
    """Minimal async client for recording audit events."""

    def __init__(self, base_url: str, internal_token: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {internal_token}"}
        self.timeout = timeout

    async def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        actor_id: str | None = None,
        actor_type: str | None = None,
        actor_display_name: str | None = None,
        source_service: str = "dfp-os",
        source_module: str | None = None,
        tenant_id: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_id": actor_id,
            "actor_type": actor_type,
            "actor_display_name": actor_display_name,
            "source_service": source_service,
            "source_module": source_module,
            "tenant_id": tenant_id,
            "before_state": before_state or {},
            "after_state": after_state or {},
            "metadata": metadata or {},
            "request_id": request_id,
            "correlation_id": correlation_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=self.timeout) as client:
            response = await client.post("/api/v1/audit-events", json=payload)
            response.raise_for_status()
            return response.json()
