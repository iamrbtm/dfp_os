from flask import Blueprint

bp = Blueprint("printers", __name__, url_prefix="/printers")

from app.blueprints.printers import routes  # noqa: E402,F401
