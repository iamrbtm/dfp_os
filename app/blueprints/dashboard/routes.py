from __future__ import annotations

from flask import render_template
from flask_login import login_required

from app.blueprints.dashboard import bp
from app.services.analytics import executive_summary, printing_analytics


@bp.get("/")
@login_required
def index():
    s = executive_summary()
    p = printing_analytics()
    dashboard_cards = [
        {"label": "Today’s Revenue", "value": f"${s['today_revenue']:,.2f}", "color": "var(--color-success)"},
        {"label": "Month Revenue", "value": f"${s['month_revenue']:,.2f}", "color": "var(--color-success)"},
        {"label": "Open Orders", "value": str(s["open_orders_count"]), "color": "var(--color-text)"},
        {"label": "Custom Requests", "value": str(s["open_custom_requests"]), "color": "var(--color-text)"},
        {"label": "Print Jobs Queued", "value": str(s["print_jobs_queued"]), "color": "var(--color-text)"},
        {"label": "Active Printers", "value": str(p["total_queued"]), "color": "var(--color-text)"},
        {"label": "Low Inventory", "value": str(s["low_inventory_count"]), "color": "var(--color-warning)" if s["low_inventory_count"] > 0 else "var(--color-text)"},
        {"label": "Low Filament", "value": str(s["low_filament_count"]), "color": "var(--color-warning)" if s["low_filament_count"] > 0 else "var(--color-text)"},
    ]
    return render_template("dashboard/index.html", dashboard_cards=dashboard_cards, upcoming_markets=s["upcoming_markets"])
