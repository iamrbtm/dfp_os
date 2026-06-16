from __future__ import annotations

from flask import jsonify, render_template

from app.blueprints.analytics import bp
from app.models import UserRole
from app.services import analytics as svc
from app.utils.auth import roles_required


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def index():
    summary = svc.executive_summary()
    product_data = svc.product_analytics(limit=5)
    market_data = svc.market_analytics()
    pos_data = svc.pos_analytics()
    print_data = svc.printing_analytics()
    inv_data = svc.inventory_analytics()
    expense_data = svc.expense_analytics()
    return render_template(
        "analytics/index.html",
        summary=summary,
        products=product_data,
        markets=market_data,
        pos=pos_data,
        printing=print_data,
        inventory=inv_data,
        expenses=expense_data,
    )


@bp.get("/data/executive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def executive_data():
    return jsonify(svc.executive_summary())


@bp.get("/data/products")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def products_data():
    limit = 20
    return jsonify(svc.product_analytics(limit=limit))


@bp.get("/data/markets")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def markets_data():
    return jsonify(svc.market_analytics())


@bp.get("/data/pos")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def pos_data():
    return jsonify(svc.pos_analytics())


@bp.get("/data/printing")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def printing_data():
    return jsonify(svc.printing_analytics())


@bp.get("/data/inventory")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def inventory_data():
    return jsonify(svc.inventory_analytics())


@bp.get("/data/expenses")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def expense_data():
    return jsonify(svc.expense_analytics())
