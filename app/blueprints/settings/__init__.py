from flask import Blueprint

bp = Blueprint("settings", __name__, url_prefix="/settings")

from app.blueprints.settings import setting_routes, theme_routes  # noqa: E402,F401
