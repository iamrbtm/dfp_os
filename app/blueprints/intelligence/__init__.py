from flask import Blueprint

bp = Blueprint("intelligence", __name__, url_prefix="/admin/intelligence")

from app.blueprints.intelligence import routes  # noqa: E402,F401
