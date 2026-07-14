from flask import Blueprint

bp = Blueprint("booth_mode", __name__, url_prefix="/booth-mode")

from app.blueprints.booth_mode import routes  # noqa: E402,F401
