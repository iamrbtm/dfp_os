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

    # Fetch the timeline for the same record. Only meaningful when
    # the event has an entity_type + entity_id; otherwise skip.
    entity_type = (event.get("entity_type") or "").strip()
    entity_id = (event.get("entity_id") or "").strip()
    timeline: list[dict] = []
    timeline_total = 0
    timeline_truncated = False
    scope = request.args.get("scope", "record")
    if scope not in ("record", "type"):
        scope = "record"
    if entity_type and (scope == "record" and entity_id):
        timeline = client.entity_timeline(
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=event.get("tenant_id"),
            limit=200,
        )
        timeline_total = len(timeline)
        timeline_truncated = len(timeline) >= 200
    elif entity_type and scope == "type":
        # "All events for this entity_type" — reuse the search
        # endpoint so the result includes every record of this
        # type, not just the current one.
        type_events = client.search(entity_type=entity_type, limit=200) or []
        # Annotate each with chain_status by walking the list in
        # ASC order; the search endpoint returns DESC.
        type_events_asc = list(reversed(type_events))
        for i, ev in enumerate(type_events_asc):
            if i == 0:
                ev["chain_status"] = "head"
            else:
                prev = type_events_asc[i - 1].get("hash")
                if ev.get("previous_hash") is None or ev.get("previous_hash") != prev:
                    ev["chain_status"] = "broken"
                else:
                    ev["chain_status"] = "ok"
        timeline = type_events_asc
        timeline_total = len(timeline)
        timeline_truncated = len(timeline) >= 200

    return_url = request.args.get("return") or request.referrer or url_for("audit_logs.index")
    # HTMX requests only want the timeline partial, not the full page.
    if request.headers.get("HX-Request") == "true" and request.args.get("partial") == "timeline":
        return render_template(
            "audit_logs/_timeline.html",
            event=event,
            timeline=timeline,
            timeline_total=timeline_total,
            timeline_truncated=timeline_truncated,
            scope=scope,
            entity_type=entity_type,
            entity_id=entity_id,
            filters=filters,
            return_url=return_url,
        )
    return render_template(
        "audit_logs/detail.html",
        event=event,
        timeline=timeline,
        timeline_total=timeline_total,
        timeline_truncated=timeline_truncated,
        scope=scope,
        entity_type=entity_type,
        entity_id=entity_id,
        filters=filters,
        return_url=return_url,
        audit_configured=client._is_configured(),
    )
