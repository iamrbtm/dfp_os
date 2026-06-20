from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.blueprints.api_tokens import bp
from app.extensions import db
from app.models import ApiToken, UserRole
from app.services.api_tokens import AVAILABLE_API_TOKEN_SCOPES, create_api_token
from app.services.audit import record_audit_event
from app.utils.auth import roles_required


@bp.route("/")
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_tokens():
    statement = select(ApiToken).where(ApiToken.user_id == current_user.id).order_by(ApiToken.created_at.desc())
    tokens = db.session.scalars(statement).all()
    return render_template("api_tokens/list.html", tokens=tokens)


@bp.route("/new", methods=["GET", "POST"], strict_slashes=False)
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_token():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        selected_scopes = [
            scope
            for scope in request.form.getlist("scopes")
            if scope in {item[0] for item in AVAILABLE_API_TOKEN_SCOPES}
        ]
        expires_at_str = request.form.get("expires_at", "").strip()

        if not name:
            flash("Token name is required.", "danger")
            return render_template("api_tokens/create.html", available_scopes=AVAILABLE_API_TOKEN_SCOPES)

        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                flash("Invalid expiration date format.", "danger")
                return render_template("api_tokens/create.html", available_scopes=AVAILABLE_API_TOKEN_SCOPES)

        token, raw_token = create_api_token(
            user=current_user,
            name=name,
            scopes=selected_scopes or None,
            expires_at=expires_at,
        )

        return render_template("api_tokens/show.html", token=token, raw_token=raw_token)

    return render_template("api_tokens/create.html", available_scopes=AVAILABLE_API_TOKEN_SCOPES)


@bp.route("/<int:token_id>")
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def token_detail(token_id: int):
    token = db.session.get(ApiToken, token_id)
    if token is None or token.user_id != current_user.id:
        flash("API token not found.", "danger")
        return redirect(url_for("api_tokens.list_tokens"))
    return render_template("api_tokens/detail.html", token=token)


@bp.route("/<int:token_id>/revoke", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def revoke_token(token_id: int):
    token = db.session.get(ApiToken, token_id)
    if token is None or token.user_id != current_user.id:
        flash("API token not found.", "danger")
        return redirect(url_for("api_tokens.list_tokens"))

    from app.models.base import utc_now
    token.revoked_at = utc_now()
    db.session.commit()
    record_audit_event(
        action="api_token.revoked",
        entity_type="api_token",
        entity_id=token.id,
        after_state={"revoked_at": token.revoked_at.isoformat()},
        source_module=__name__,
        actor_id=current_user.id,
    )
    flash("API token revoked.", "success")
    return redirect(url_for("api_tokens.list_tokens"))
