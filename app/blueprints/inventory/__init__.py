from flask import Blueprint

bp = Blueprint("inventory", __name__, url_prefix="/inventory")

from app.blueprints.inventory import routes  # noqa: E402,F401
