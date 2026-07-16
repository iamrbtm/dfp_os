from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.blueprints.feature_flags import bp
from app.extensions import db
from app.models import FeatureFlag, UserRole
from app.module_registry import module_statuses
from app.services.audit import record_audit_event
from app.utils.auth import roles_required


@bp.route("/")
@login_required
@roles_required(UserRole.ADMIN)
def index():
    search = request.args.get("q", "").strip()
    query = select(FeatureFlag).order_by(FeatureFlag.key)
    if search:
        query = query.where(
            FeatureFlag.key.ilike(f"%{search}%")
            | FeatureFlag.description.ilike(f"%{search}%")
        )
    flags = db.session.scalars(query).all()
    modules = module_statuses()
    return render_template("admin/feature_flags/index.html", flags=flags, search=search, modules=modules)


@bp.route("/<int:flag_id>/toggle", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def toggle(flag_id: int):
    flag = db.session.get(FeatureFlag, flag_id)
    if flag is None:
        flash("Feature flag not found.", "danger")
        return redirect(url_for("feature_flags.index"))

    before_state = {"enabled": flag.enabled}
    flag.enabled = not flag.enabled
    db.session.commit()

    record_audit_event(
        action="feature_flag.toggled",
        entity_type="feature_flag",
        entity_id=flag.key,
        before_state=before_state,
        after_state={"enabled": flag.enabled},
        source_module=__name__,
        actor_id=current_user.id,
    )

    status = "enabled" if flag.enabled else "disabled"
    flash(f"Feature flag '{flag.key}' {status}.", "success")
    return redirect(url_for("feature_flags.index"))
