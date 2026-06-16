from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.settings import bp
from app.models import UserRole
from app.services.settings import get_all_settings, set_setting
from app.utils.auth import roles_required


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
        set_setting(key, value)
        keys_updated += 1
    flash(f"{keys_updated} settings updated.", "success")
    return redirect(url_for("settings.settings_list"))


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
