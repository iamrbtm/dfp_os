from flask import Blueprint

bp = Blueprint("markets", __name__, url_prefix="/markets")

from app.blueprints.markets import routes  # noqa: E402,F401
