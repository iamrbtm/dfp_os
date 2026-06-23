from flask import Blueprint

bp = Blueprint("prep_tasks", __name__, url_prefix="/prep-tasks")

from app.blueprints.prep_tasks import routes  # noqa: E402,F401
