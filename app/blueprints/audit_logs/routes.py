from __future__ import annotations

from flask import abort, render_template, request, url_for

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
    return render_template(
        "audit_logs/index.html",
        events=events or [],
        filters=filters,
        audit_configured=client._is_configured(),
    )


@bp.get("/<event_id>")
@roles_required(UserRole.ADMIN)
def detail(event_id: str):
    client = get_audit_client()
    event = client.get(event_id) if hasattr(client, "get") else None
    if event is None:
        abort(404)
    filters = {k: request.args.get(k) for k in ("action", "entity_type", "entity_id", "actor_id")}
    return_url = request.args.get("return") or request.referrer or url_for("audit_logs.index")
    return render_template(
        "audit_logs/detail.html",
        event=event,
        filters=filters,
        return_url=return_url,
        audit_configured=client._is_configured(),
    )
