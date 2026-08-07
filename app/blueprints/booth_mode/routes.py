from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.booth_mode import bp
from app.extensions import db
from app.models import BoothHintStatus, BoothModeHint, Market, PosSession, UserRole
from app.module_registry import is_module_enabled
from app.services.audit import record_audit_event
from app.services.booth_mode import booth_mode_context, update_hint_status
from app.utils.auth import roles_required


@bp.before_request
def enforce_booth_mode_flag():
    if not is_module_enabled("booth_mode"):
        abort(403)


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def index():
    market_id = request.args.get("market_id", type=int)
    session_id = request.args.get("session_id", type=int)
    markets = Market.query.order_by(Market.event_date.desc(), Market.name).limit(30).all()
    sessions = PosSession.query.order_by(PosSession.id.desc()).limit(30).all()
    try:
        context = booth_mode_context(market_id=market_id, session_id=session_id)
        record_audit_event(
            action="booth_mode.viewed",
            entity_type="pos_session",
            entity_id=context["session"].id,
            after_state={
                "session_id": context["session"].id,
                "market_id": market_id,
            },
            source_module=__name__,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        context = None
        flash(str(exc), "warning")
    return render_template(
        "booth_mode/index.html",
        booth=context,
        markets=markets,
        sessions=sessions,
        selected_market_id=market_id,
        selected_session_id=session_id,
    )


@bp.get("/stats")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def stats():
    """HTMX fragment endpoint — returns only the refreshable stats section."""
    market_id = request.args.get("market_id", type=int)
    session_id = request.args.get("session_id", type=int)
    try:
        context = booth_mode_context(market_id=market_id, session_id=session_id)
    except ValueError:
        context = None
    return render_template(
        "booth_mode/_stats.html",
        booth=context,
        selected_market_id=market_id,
        selected_session_id=session_id,
    )


@bp.post("/hints/<int:hint_id>/<status>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def hint_status(hint_id: int, status: str):
    hint = db.session.get(BoothModeHint, hint_id)
    if hint is None:
        flash("Hint not found.", "danger")
        return redirect(url_for("booth_mode.index"))
    try:
        new_status = BoothHintStatus(status)
    except ValueError:
        flash("Unsupported hint action.", "danger")
        return redirect(url_for("booth_mode.index"))
    update_hint_status(hint, new_status, actor_id=current_user.id)
    flash("Booth hint updated.", "success")
    return redirect(
        url_for("booth_mode.index", session_id=hint.pos_session_id, market_id=hint.market_id)
    )
