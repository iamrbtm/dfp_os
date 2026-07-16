from flask import Blueprint

bp = Blueprint("feature_flags", __name__, url_prefix="/admin/feature-flags")

from app.blueprints.feature_flags import routes  # noqa: E402,F401
