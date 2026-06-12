from __future__ import annotations

from flask import render_template
from flask_login import login_required

from app.blueprints.dashboard import bp


@bp.get("/")
@login_required
def index():
    dashboard_cards = [
        {"label": "Today’s POS Revenue", "value": "Coming soon"},
        {"label": "Orders in Production", "value": "Coming soon"},
        {"label": "Low Inventory Alerts", "value": "Coming soon"},
        {"label": "Upcoming Markets", "value": "Coming soon"},
    ]
    return render_template("dashboard/index.html", dashboard_cards=dashboard_cards)
