from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import flash, g, jsonify, redirect, request, url_for
from flask_login import current_user

from app.models import UserRole
from app.services.api_tokens import authenticate_api_token


def roles_required(*allowed_roles: UserRole):
    def decorator(view: Callable):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))

            if current_user.role not in allowed_roles:
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
