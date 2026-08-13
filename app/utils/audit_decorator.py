"""Decorators and helpers for emitting audit events from view/service code.

The whole audit story is centralised in ``app.services.audit`` —
``record_audit_event`` already pulls the request id, IP, and user agent
from ``flask.g`` and the actor from ``flask_login.current_user``. The
``@audited`` decorator here layers ergonomics on top: it captures the
route, blueprint, status code, and timing automatically, and it lets a
caller mark a view as ``critical=True`` (financial) so the outbox
fail-closed behaviour triggers correctly.
"""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable

from flask import has_request_context, request

logger = logging.getLogger(__name__)


def audited(
    *,
    action: str,
    entity_type: str,
    entity_id_arg: str | None = None,
    critical: bool = False,
    source_module: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: emit an audit event after a view/service runs.

    Parameters
    ----------
    action:
        Audit action name (typically a member of ``AuditAction``).
    entity_type:
        The kind of entity the view operates on (``"order"``, ``"product"``).
    entity_id_arg:
        Name of the kwarg / positional argument whose value should be used
        as the entity id. ``None`` means "no entity id" (e.g. list views).
    critical:
        Mark as a financial / must-not-be-lost event. When ``True`` the
        audit client will raise ``AuditDispatchError`` if the microservice
        and the outbox are both unavailable.
    source_module:
        Override the auto-derived source module (``__name__`` of the
        decorated function's module).
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from app.services.audit import record_audit_event

            started = time.perf_counter()
            response = view(*args, **kwargs)
            try:
                entity_id: str | int | None = None
                if entity_id_arg:
                    entity_id = kwargs.get(entity_id_arg)
                    if entity_id is None and args:
                        try:
                            entity_id = args[1]
                        except IndexError:
                            entity_id = None
                status_code = getattr(response, "status_code", 200)
                metadata: dict[str, Any] = {
                    "status_code": status_code,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
                if has_request_context():
                    metadata["endpoint"] = request.endpoint
                    metadata["view_args"] = {k: v for k, v in request.view_args.items()} or None
                record_audit_event(
                    action=action,
                    entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None,
                    source_module=source_module or view.__module__,
                    critical=critical,
                    metadata=metadata,
                )
            except Exception as exc:
                logger.warning("audited decorator failed to emit %s: %s", action, exc)
            return response

        wrapper._audited = True  # type: ignore[attr-defined]
        return wrapper

    return decorator
