from flask import Blueprint

bp = Blueprint("print_jobs", __name__, url_prefix="/print-jobs")

from app.blueprints.print_jobs import routes  # noqa: E402,F401
