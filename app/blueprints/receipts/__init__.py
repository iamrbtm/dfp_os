from flask import Blueprint

bp = Blueprint("receipts", __name__, url_prefix="/expenses/receipts")

from app.blueprints.receipts import routes  # noqa: E402,F401
