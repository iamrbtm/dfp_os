from __future__ import annotations

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from app.blueprints.settings import bp
from app.extensions import db
from app.theme_registry import ALL_THEMES, DEFAULT_THEME, THEME_MAP, is_valid_theme
from app.services.audit import record_audit_event
from app.services.settings import set_setting
from app.utils.auth import roles_required
from app.models.user import UserRole


@bp.route("/themes")
@login_required
def themes():
    themes = ALL_THEMES
    current_theme = current_user.theme_slug
    return render_template(
        "settings/themes.html",
        themes=themes,
        current_theme=current_theme,
        default_theme=DEFAULT_THEME,
    )


@bp.route("/themes/apply", methods=["POST"])
@login_required
def apply_theme():
    data = request.get_json(force=True)
    slug = data.get("theme_slug", "").strip()
    if not is_valid_theme(slug):
        return jsonify({"error": "Invalid theme slug"}), 400
    before_state = {"theme_slug": current_user.theme_slug}
    current_user.theme_slug = slug
    db.session.commit()
    record_audit_event(
        action="user.theme_updated",
        entity_type="user",
        entity_id=current_user.id,
        before_state=before_state,
        after_state={"theme_slug": current_user.theme_slug},
        source_module=__name__,
        actor_id=current_user.id,
    )
    return jsonify({"theme_slug": slug})


@bp.route("/themes/default", methods=["POST"])
@roles_required(UserRole.ADMIN)
def set_default_theme():
    data = request.get_json(force=True)
    slug = data.get("theme_slug", "").strip()
    if not is_valid_theme(slug):
        return jsonify({"error": "Invalid theme slug"}), 400
    from flask import current_app
    before_state = {"default_theme": current_app.config.get("DEFAULT_THEME", DEFAULT_THEME)}
    current_app.config["DEFAULT_THEME"] = slug
    set_setting("default_theme", slug)
    record_audit_event(
        action="theme.default_updated",
        entity_type="setting",
        entity_id="default_theme",
        before_state=before_state,
        after_state={"default_theme": slug},
        source_module=__name__,
        actor_id=current_user.id,
    )
    return jsonify({"theme_slug": slug})


@bp.route("/api/themes")
def api_list_themes():
    result = []
    for t in ALL_THEMES:
        result.append({
            "slug": t.slug,
            "name": t.name,
            "mode": t.mode,
            "description": t.description,
        })
    return jsonify(result)


@bp.route("/api/themes/current")
@login_required
def api_current_theme():
    return jsonify({
        "slug": current_user.theme_slug,
        "name": THEME_MAP[current_user.theme_slug].name if current_user.theme_slug in THEME_MAP else DEFAULT_THEME,
        "mode": THEME_MAP[current_user.theme_slug].mode if current_user.theme_slug in THEME_MAP else "light",
    })


@bp.route("/api/users/me/theme", methods=["PATCH"])
@login_required
def api_update_user_theme():
    data = request.get_json(force=True)
    slug = data.get("theme_slug", "").strip()
    if not is_valid_theme(slug):
        return jsonify({"error": "Invalid theme slug"}), 400
    before_state = {"theme_slug": current_user.theme_slug}
    current_user.theme_slug = slug
    db.session.commit()
    record_audit_event(
        action="user.theme_updated",
        entity_type="user",
        entity_id=current_user.id,
        before_state=before_state,
        after_state={"theme_slug": current_user.theme_slug},
        source_module=__name__,
        actor_id=current_user.id,
    )
    return jsonify({"theme_slug": slug})
