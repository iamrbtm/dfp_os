from flask import Blueprint

bp = Blueprint("internal_api", __name__, url_prefix="/api/internal")

from app.blueprints.internal_api import routes  # noqa: E402,F401
