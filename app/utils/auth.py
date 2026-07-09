from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import current_app, flash, g, jsonify, redirect, request, url_for
from flask_login import current_user

from app.models import UserRole
from app.services.api_tokens import authenticate_api_token
from app.services.audit import record_audit_event
from app.utils.rate_limit import client_key, is_limited


def roles_required(*allowed_roles: UserRole):
    def decorator(view: Callable):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))

            if current_user.role not in allowed_roles:
                record_audit_event(
                    action="authorization.failed",
                    entity_type="route",
                    entity_id=request.endpoint,
                    metadata={
                        "required_roles": [role.value for role in allowed_roles],
                        "user_role": current_user.role.value,
                    },
                    source_module=__name__,
                )
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard.index"))

            return view(*args, **kwargs)

        return wrapped

    return decorator


def api_token_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        raw_token = request.headers.get("X-API-Token")

        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()

        if not raw_token:
            if is_limited(
                client_key("api_auth"),
                limit=current_app.config.get("API_AUTH_RATE_LIMIT_ATTEMPTS", 60),
                window_seconds=current_app.config.get("API_AUTH_RATE_LIMIT_WINDOW_SECONDS", 60),
            ):
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "rate_limited",
                                "message": "Too many API authentication failures.",
                                "details": {},
                            }
                        }
                    ),
                    429,
                )
            record_audit_event(
                action="api_token.missing",
                entity_type="api_request",
                entity_id=request.path,
                source_module=__name__,
                actor_type="anonymous",
            )
            return (
                jsonify(
                    {
                        "error": {
                            "code": "missing_api_token",
                            "message": "An API token is required.",
                            "details": {},
                        }
                    }
                ),
                401,
            )

        token = authenticate_api_token(raw_token)
        if token is None:
            if is_limited(
                client_key("api_auth"),
                limit=current_app.config.get("API_AUTH_RATE_LIMIT_ATTEMPTS", 60),
                window_seconds=current_app.config.get("API_AUTH_RATE_LIMIT_WINDOW_SECONDS", 60),
            ):
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "rate_limited",
                                "message": "Too many API authentication failures.",
                                "details": {},
                            }
                        }
                    ),
                    429,
                )
            record_audit_event(
                action="api_token.invalid",
                entity_type="api_request",
                entity_id=request.path,
                source_module=__name__,
                actor_type="anonymous",
            )
            return (
                jsonify(
                    {
                        "error": {
                            "code": "invalid_api_token",
                            "message": "The provided API token is invalid.",
                            "details": {},
                        }
                    }
                ),
                401,
            )

        g.api_token = token
        g.api_user = token.user
        return view(*args, **kwargs)

    return wrapped


def require_api_scopes(*required_scopes: str):
    token = getattr(g, "api_token", None)
    if token is None or not required_scopes:
        return None
    if token.has_scope(*required_scopes):
        return None

    record_audit_event(
        action="api_token.scope_denied",
        entity_type="api_request",
        entity_id=request.path,
        source_module=__name__,
        actor_id=getattr(token, "id", None),
        actor_type="api_token",
        metadata={"required_scopes": list(required_scopes), "token_scopes": sorted(token.scope_set)},
    )
    return (
        jsonify(
            {
                "error": {
                    "code": "insufficient_scope",
                    "message": "The API token does not have the required scope for this resource.",
                    "details": {"required_scopes": list(required_scopes)},
                }
            }
        ),
        403,
    )
