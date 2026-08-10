from flask import Blueprint

bp = Blueprint("market_catalog", __name__, url_prefix="/market-catalog")

from app.blueprints.market_catalog import routes  # noqa: E402,F401
