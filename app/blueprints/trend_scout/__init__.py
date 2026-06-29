from flask import Blueprint

bp = Blueprint("trend_scout", __name__, url_prefix="/admin/trend-scout")

from app.blueprints.trend_scout import routes  # noqa: E402, F401
