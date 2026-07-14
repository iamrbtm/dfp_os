from flask import Blueprint

bp = Blueprint("report_studio", __name__, url_prefix="/report-studio")

from app.blueprints.report_studio import routes  # noqa: E402,F401
