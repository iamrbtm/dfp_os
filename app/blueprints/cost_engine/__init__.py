from flask import Blueprint

bp = Blueprint("cost_engine", __name__, url_prefix="/cost-engine")

from app.blueprints.cost_engine import routes  # noqa: E402,F401
