from flask import Blueprint

bp = Blueprint("promotion", __name__, url_prefix="/promotion")

from app.blueprints.promotion import routes  # noqa: E402,F401
