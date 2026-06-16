from flask import Blueprint

bp = Blueprint("custom_orders", __name__, url_prefix="/custom-orders")

from app.blueprints.custom_orders import routes  # noqa: E402,F401
