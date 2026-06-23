from __future__ import annotations

from flask import render_template, request

from app.blueprints.audit_logs import bp
from app.services.audit_client import get_audit_client
from app.utils.auth import roles_required
from app.models import UserRole


@bp.get("/")
@roles_required(UserRole.ADMIN)
def index():
    client = get_audit_client()
    filters = {
        "action": request.args.get("action", "").strip() or None,
        "entity_type": request.args.get("entity_type", "").strip() or None,
        "entity_id": request.args.get("entity_id", "").strip() or None,
        "actor_id": request.args.get("actor_id", "").strip() or None,
        "limit": request.args.get("limit", 50, type=int),
        "offset": request.args.get("offset", 0, type=int),
    }
    events = client.search(**filters) if hasattr(client, "search") else []
    return render_template("audit_logs/index.html", events=events or [], filters=filters, audit_configured=client._is_configured())
