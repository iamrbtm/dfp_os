from flask import Blueprint

bp = Blueprint("api_tokens", __name__, url_prefix="/settings/api-tokens")

from app.blueprints.api_tokens import routes  # noqa: E402,F401
