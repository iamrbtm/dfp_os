from flask import Blueprint

bp = Blueprint("products", __name__, url_prefix="/products")

from app.blueprints.products import routes  # noqa: E402,F401
