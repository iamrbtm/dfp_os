from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.blueprints.settings import bp
from app.extensions import db
from app.forms.admin import BusinessForm, FeatureFlagForm
from app.models import Business, FeatureFlag, Setting, UserRole
from app.services.settings import get_all_settings, set_setting
from app.module_registry import module_statuses
from app.services.business import ensure_default_business
from app.services.audit import record_audit_event
from app.utils.auth import roles_required

CRITICAL_MODULE_KEYS = {"public_site", "auth", "dashboard", "settings"}


@bp.route("/")
@login_required
@roles_required(UserRole.ADMIN)
def settings_list():
    settings = get_all_settings()
    return render_template("settings/settings.html", setting_groups=_group_settings(settings))


@bp.route("/update", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def settings_update():
    keys_updated = 0
    for key, value in request.form.items():
        if key in ("csrf_token",):
            continue
        existing = db.session.scalar(select(Setting).where(Setting.key == key))
        before = {"key": key, "value": existing.value, "type": existing.type} if existing else None
        set_setting(key, value)
        record_audit_event(
            action="settings.changed",
            entity_type="setting",
            entity_id=key,
            before_state=before,
            after_state={"key": key, "value": value, "type": existing.type if existing else "string"},
            source_module=__name__,
            actor_id=current_user.id,
        )
        keys_updated += 1
    flash(f"{keys_updated} settings updated.", "success")
    return redirect(url_for("settings.settings_list"))


@bp.route("/modules")
@login_required
@roles_required(UserRole.ADMIN)
def module_status():
    flags = FeatureFlag.query.order_by(FeatureFlag.key).all()
    return render_template("settings/modules.html", modules=module_statuses(), flags=flags)


@bp.route("/business", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN)
def business_settings():
    business = ensure_default_business()
    form = _build_form(BusinessForm, business)
    if form.validate_on_submit():
        before_state = {
            "name": business.name,
            "slug": business.slug,
            "contact_email": business.contact_email,
            "city": business.city,
            "state": business.state,
        }
        form.apply(business)
        db.session.commit()
        record_audit_event(
            action="business.updated",
            entity_type="business",
            entity_id=business.id,
            before_state=before_state,
            after_state={"name": business.name, "slug": business.slug, "contact_email": business.contact_email},
            source_module=__name__,
            actor_id=current_user.id,
            business_id=business.id,
        )
        flash("Business settings updated.", "success")
        return redirect(url_for("settings.business_settings"))
    return render_template("settings/business.html", form=form, business=business)


@bp.route("/feature-flags")
@login_required
@roles_required(UserRole.ADMIN)
def feature_flags():
    flags = FeatureFlag.query.order_by(FeatureFlag.key).all()
    return render_template("settings/feature_flags.html", flags=flags)


@bp.route("/feature-flags/new", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN)
def feature_flag_new():
    form = FeatureFlagForm()
    if form.validate_on_submit():
        flag = FeatureFlag()
        form.apply(flag)
        db.session.add(flag)
        db.session.commit()
        record_audit_event(
            action="feature_flag.created",
            entity_type="feature_flag",
            entity_id=flag.id,
            after_state={"key": flag.key, "enabled": flag.enabled, "business_id": flag.business_id},
            source_module=__name__,
            actor_id=current_user.id,
        )
        flash("Feature flag created.", "success")
        return redirect(url_for("settings.feature_flags"))
    return render_template("settings/feature_flag_form.html", form=form, mode="create")


@bp.route("/feature-flags/<int:flag_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN)
def feature_flag_edit(flag_id: int):
    flag = db.session.get(FeatureFlag, flag_id)
    if flag is None:
        return render_template("errors/404.html"), 404
    form = _build_form(FeatureFlagForm, flag)
    if form.validate_on_submit():
        before_state = {"key": flag.key, "enabled": flag.enabled, "business_id": flag.business_id}
        form.apply(flag)
        db.session.commit()
        record_audit_event(
            action="feature_flag.updated",
            entity_type="feature_flag",
            entity_id=flag.id,
            before_state=before_state,
            after_state={"key": flag.key, "enabled": flag.enabled, "business_id": flag.business_id},
            source_module=__name__,
            actor_id=current_user.id,
        )
        flash("Feature flag updated.", "success")
        return redirect(url_for("settings.feature_flags"))
    return render_template("settings/feature_flag_form.html", form=form, mode="edit", flag=flag)


@bp.post("/modules/update")
@login_required
@roles_required(UserRole.ADMIN)
def module_status_update():
    skipped_modules: list[str] = []
    for module in module_statuses():
        key = module["feature_flag_key"]
        enabled = request.form.get(key) == "on"
        if module["key"] in CRITICAL_MODULE_KEYS and not enabled:
            skipped_modules.append(module["display_name"])
            enabled = True
        record = FeatureFlag.query.filter_by(key=key).first()
        before_state = {"enabled": module["enabled"]}
        if record is None:
            record = FeatureFlag(key=key, enabled=enabled, description=f"Override for {module['display_name']}")
            db.session.add(record)
        else:
            record.enabled = enabled
        record_audit_event(
            action="module.status_changed",
            entity_type="module",
            entity_id=module["key"],
            before_state=before_state,
            after_state={"enabled": enabled, "feature_flag_key": key},
            source_module=__name__,
            actor_id=current_user.id,
        )
    db.session.commit()
    if skipped_modules:
        flash(
            "Protected core modules were left enabled: " + ", ".join(skipped_modules) + ".",
            "warning",
        )
    flash("Module settings updated.", "success")
    return redirect(url_for("settings.module_status"))


def _group_settings(settings: list) -> dict[str, list]:
    groups: dict[str, list] = {
        "Store": [],
        "POS": [],
        "System": [],
    }
    store_keys = {"store_name", "store_tagline", "store_email", "store_phone",
                  "store_address", "store_city", "store_state", "store_zip",
                  "currency_symbol", "tax_rate"}
    pos_keys = {"pos_default_opening_cash", "pos_card_processor", "pos_card_processing_enabled"}
    for s in settings:
        if s.key in store_keys:
            groups["Store"].append(s)
        elif s.key in pos_keys:
            groups["POS"].append(s)
        else:
            groups["System"].append(s)
    return {k: v for k, v in groups.items() if v}


def _build_form(form_class, instance):
    data = {}
    form = form_class()
    form.instance_id = instance.id
    for field_name in form._fields:
        if field_name in {"csrf_token", "submit"}:
            continue
        value = getattr(instance, field_name, None)
        data[field_name] = value
    form = form_class(data=data)
    form.instance_id = instance.id
    return form
