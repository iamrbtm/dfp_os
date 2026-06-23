from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from flask import current_app


class AuditClient:
    """Synchronous HTTP client for the audit-log microservice."""

    def __init__(self, base_url: str | None = None, token: str | None = None, enabled: bool = True):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled

    def _is_configured(self) -> bool:
        if not self.enabled:
            return False
        if not self.base_url or not self.token:
            return False
        return True

    def record(
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
    ) -> dict[str, Any] | None:
        if not self._is_configured():
            return None

        payload = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_id": str(actor_id) if actor_id is not None else None,
            "actor_type": actor_type,
            "actor_display_name": actor_display_name,
            "source_service": source_service,
            "source_module": source_module,
            "tenant_id": tenant_id,
            "before_state": before_state or {},
            "after_state": after_state or {},
            "metadata": metadata or {},
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            ) as client:
                response = client.post("/api/v1/audit-events", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            current_app.logger.warning("audit-log unavailable: %s", e)
        except httpx.HTTPStatusError as e:
            current_app.logger.warning("audit-log error: %s", e)
        except Exception as e:
            current_app.logger.warning("audit-log client failed: %s", e)
        return None

    def record_batch(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self._is_configured():
            return None
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15.0,
            ) as client:
                response = client.post("/api/v1/audit-events/batch", json={"events": events})
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            current_app.logger.warning("audit-log unavailable: %s", e)
        except httpx.HTTPStatusError as e:
            current_app.logger.warning("audit-log error: %s", e)
        except Exception as e:
            current_app.logger.warning("audit-log client failed: %s", e)
        return None

    def search(self, **params: Any) -> list[dict[str, Any]]:
        if not self._is_configured():
            return []
        query = {key: value for key, value in params.items() if value not in (None, "", [])}
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            ) as client:
                response = client.get("/api/v1/audit-events", params=query)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            current_app.logger.warning("audit-log unavailable: %s", e)
        except httpx.HTTPStatusError as e:
            current_app.logger.warning("audit-log error: %s", e)
        except Exception as e:
            current_app.logger.warning("audit-log client failed: %s", e)
        return []


def get_audit_client() -> AuditClient:
    config = current_app.config
    return AuditClient(
        base_url=config.get("AUDIT_LOG_BASE_URL", ""),
        token=config.get("AUDIT_LOG_TOKEN", ""),
        enabled=config.get("AUDIT_LOG_ENABLED", False),
    )
