from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from flask import current_app, g, has_request_context, request

from app.services import audit_outbox

logger = logging.getLogger(__name__)


class AuditDispatchError(RuntimeError):
    """Raised when a critical audit event cannot be dispatched."""


class AuditClient:
    """Synchronous HTTP client for the audit-log microservice.

    The client follows an "outbox-first" delivery model:

    1. Try a direct ``POST`` to the microservice.
    2. If the service is unreachable or returns 5xx, push the event onto
       a Redis-backed outbox (``app.services.audit_outbox``) so a Celery
       beat task can replay it once the service recovers.
    3. If the outbox is also unavailable, deadman the event to disk so
       nothing is lost silently. The next startup will replay the
       deadman directory.

    For ``critical=True`` events the failure mode is fail-closed: if
    neither the direct POST nor the outbox nor the deadman can persist
    the event, the call raises ``AuditDispatchError``. Combined with
    ``AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS=true`` this is what
    protects financial writes.
    """

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

    def _request_context(self) -> dict[str, Any]:
        """Auto-fill request_id, ip, user_agent, actor from ``g``/``current_user``."""
        if not has_request_context():
            return {}
        return {
            "request_id": getattr(g, "request_id", None),
            "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
            "user_agent": request.headers.get("User-Agent"),
        }

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
        critical: bool = False,
    ) -> dict[str, Any] | None:
        if not self._is_configured():
            if critical and self.enabled and current_app.config.get("AUDIT_LOG_FAIL_CLOSED", False):
                raise AuditDispatchError(
                    "Critical audit event could not be dispatched: audit-log is not configured"
                )
            return None

        ctx = self._request_context()
        payload: dict[str, Any] = {
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
            "request_id": ctx.get("request_id"),
            "ip_address": ctx.get("ip_address"),
            "user_agent": ctx.get("user_agent"),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        payload["critical"] = critical

        # Try the synchronous path first.
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            ) as client:
                response = client.post("/api/v1/audit-events", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as exc:
            self._handle_outbox_failure(payload, exc, critical, reason="network_error")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if 500 <= status < 600:
                self._handle_outbox_failure(payload, exc, critical, reason=f"http_{status}")
            else:
                logger.warning("audit-log non-retryable error: %s", exc)
                if critical and current_app.config.get("AUDIT_LOG_FAIL_CLOSED", False):
                    raise AuditDispatchError("Critical audit event rejected") from exc
        except Exception as exc:
            self._handle_outbox_failure(payload, exc, critical, reason="unexpected_error")
        return None

    def _handle_outbox_failure(
        self,
        payload: dict[str, Any],
        exc: Exception,
        critical: bool,
        *,
        reason: str,
    ) -> None:
        """Buffer the event in Redis, or fail closed if critical and no buffer."""
        logger.warning("audit-log %s; buffering to outbox: %s", reason, exc)
        enqueued = audit_outbox.enqueue(payload, critical=critical)
        if (
            not enqueued
            and critical
            and current_app.config.get("AUDIT_LOG_FAIL_CLOSED_FOR_FINANCIAL_ACTIONS", False)
        ):
            raise AuditDispatchError(
                f"Critical audit event could not be persisted (outbox full or down): {reason}"
            ) from exc

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
            logger.warning("audit-log unavailable: %s", e)
        except httpx.HTTPStatusError as e:
            logger.warning("audit-log error: %s", e)
        except Exception as e:
            logger.warning("audit-log client failed: %s", e)
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

    def get(self, event_id: str) -> dict[str, Any] | None:
        if not self._is_configured():
            return None
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            ) as client:
                response = client.get(f"/api/v1/audit-events/{event_id}")
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            current_app.logger.warning("audit-log unavailable: %s", e)
        except httpx.HTTPStatusError as e:
            current_app.logger.warning("audit-log error: %s", e)
        except Exception as e:
            current_app.logger.warning("audit-log client failed: %s", e)
        return None

    def flush_outbox(self) -> dict[str, int]:
        """Drain the Redis outbox by replaying every queued event through the
        synchronous record path. Called by the Celery beat task.
        """
        if not self._is_configured():
            return {"drained": 0, "remaining": audit_outbox.size()}
        drained = 0
        failed = 0
        batch_size = int(current_app.config.get("AUDIT_OUTBOX_BATCH_SIZE", 200))
        for _ in range(batch_size):
            event = audit_outbox.drain_one()
            if event is None:
                break
            # We popped the event already; if delivery fails we put it back.
            try:
                self._dispatch_raw(event)
                drained += 1
            except Exception as exc:
                failed += 1
                logger.warning("audit outbox replay failed (%s); leaving in queue", exc)
                audit_outbox.enqueue(event, critical=event.get("critical", False))
                # Stop hammering a service that is still down.
                break
        return {
            "drained": drained,
            "failed": failed,
            "remaining": audit_outbox.size(),
        }

    def _dispatch_raw(self, event: dict[str, Any]) -> None:
        """Send a queued event without re-buffering (to avoid loops)."""
        with httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=10.0,
        ) as client:
            response = client.post("/api/v1/audit-events", json=event)
            response.raise_for_status()


def get_audit_client() -> AuditClient:
    config = current_app.config
    return AuditClient(
        base_url=config.get("AUDIT_LOG_BASE_URL", ""),
        token=config.get("AUDIT_LOG_TOKEN", ""),
        enabled=config.get("AUDIT_LOG_ENABLED", False),
    )
