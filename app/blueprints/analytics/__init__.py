from flask import Blueprint

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

from app.blueprints.analytics import routes  # noqa: E402, F401
