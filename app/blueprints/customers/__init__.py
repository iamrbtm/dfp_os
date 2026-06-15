from flask import Blueprint

bp = Blueprint("customers", __name__, url_prefix="/customers")

from app.blueprints.customers import routes  # noqa: E402,F401
