from flask import Blueprint

bp = Blueprint(
    "table_layouts",
    __name__,
    url_prefix="/table_layouts",
    template_folder="../../templates",
)

from app.blueprints.table_layouts import routes  # noqa: E402, F401
