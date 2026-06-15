from flask import Blueprint

bp = Blueprint("orders", __name__, url_prefix="/orders")

from app.blueprints.orders import routes  # noqa: E402,F401
