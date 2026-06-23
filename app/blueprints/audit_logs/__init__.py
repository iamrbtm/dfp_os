from flask import Blueprint

bp = Blueprint("audit_logs", __name__, url_prefix="/audit-logs")

from app.blueprints.audit_logs import routes  # noqa: E402,F401
