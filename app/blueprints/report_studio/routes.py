from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.blueprints.report_studio import bp
from app.models import UserRole
from app.services.report_studio import (
    get_data_quality_summary,
    get_market_application_pipeline_report,
    get_report_catalog,
    get_vendor_market_heat_map,
)
from app.utils.auth import roles_required


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def home():
    catalog = get_report_catalog()
    data_quality = get_data_quality_summary()
    category_filter = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()

    if category_filter:
        catalog = [r for r in catalog if r.get("category", "").lower() == category_filter.lower()]
    if search:
        catalog = [
            r
            for r in catalog
            if search.lower() in (r.get("title", "") + r.get("description", "") + r.get("category", "")).lower()
        ]

    return render_template(
        "report_studio/home.html",
        catalog=catalog,
        data_quality=data_quality,
        category_filter=category_filter,
        search=search,
    )


@bp.get("/heat-map")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def heat_map():
    data = get_vendor_market_heat_map(request.args)
    return render_template(
        "report_studio/heat_map.html",
        markets=data,
        min_profit=request.args.get("min_profit", ""),
        status_filter=request.args.get("status", "").strip(),
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        location_filter=request.args.get("location", ""),
    )


@bp.get("/application-tracker")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def application_tracker():
    data = get_market_application_pipeline_report(request.args)
    return render_template(
        "report_studio/application_tracker.html",
        report=data,
    )
