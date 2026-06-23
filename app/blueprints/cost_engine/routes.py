from __future__ import annotations

from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for

from app.blueprints.cost_engine import bp
from app.models import Market, Order, Product, ProductVariant, UserRole
from app.services.cost_engine import calculate_product_cost, estimate_market_profit, estimate_order_profit
from app.services.settings import get_setting_typed, set_setting
from app.utils.auth import roles_required


def _decimal_setting(key: str, default: str) -> Decimal:
    value = get_setting_typed(key, default)
    return Decimal(str(value or default))


@bp.route("/", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def index():
    if request.method == "POST":
        for key in (
            "cost_engine_cost_per_gram",
            "cost_engine_labor_rate",
            "cost_engine_packaging_cost",
            "cost_engine_machine_hour_rate",
            "cost_engine_failure_rate",
            "cost_engine_target_margin_percent",
        ):
            set_setting(key, request.form.get(key, "").strip() or "0", type="decimal")
        flash("Cost engine settings saved.", "success")
        return redirect(url_for("cost_engine.index"))

    products = Product.query.order_by(Product.name).all()
    orders = Order.query.order_by(Order.created_at.desc()).limit(50).all()
    markets = Market.query.order_by(Market.event_date.desc()).limit(50).all()

    selected_product = request.args.get("product_id", type=int)
    selected_variant = request.args.get("variant_id", type=int)
    selected_order = request.args.get("order_id", type=int)
    selected_market = request.args.get("market_id", type=int)

    settings = {
        "cost_per_gram": _decimal_setting("cost_engine_cost_per_gram", "0.025"),
        "labor_rate": _decimal_setting("cost_engine_labor_rate", "18.00"),
        "packaging_cost": _decimal_setting("cost_engine_packaging_cost", "0.50"),
        "machine_hour_rate": _decimal_setting("cost_engine_machine_hour_rate", "0.50"),
        "failure_rate": _decimal_setting("cost_engine_failure_rate", "0.05"),
        "target_margin_percent": _decimal_setting("cost_engine_target_margin_percent", "55.00"),
    }

    product_breakdown = None
    if selected_product:
        product = Product.query.get(selected_product)
        variant = ProductVariant.query.get(selected_variant) if selected_variant else None
        if product:
            product_breakdown = calculate_product_cost(
                product=product,
                variant=variant,
                cost_per_gram=settings["cost_per_gram"],
                labor_rate=settings["labor_rate"],
                packaging_cost=settings["packaging_cost"],
                machine_hour_rate=settings["machine_hour_rate"],
                failure_rate=settings["failure_rate"],
                target_margin_percent=settings["target_margin_percent"],
            )

    order_profit = estimate_order_profit(selected_order) if selected_order else None
    market_profit = estimate_market_profit(selected_market) if selected_market else None

    return render_template(
        "cost_engine/index.html",
        products=products,
        orders=orders,
        markets=markets,
        settings=settings,
        product_breakdown=product_breakdown,
        selected_product=selected_product,
        selected_variant=selected_variant,
        selected_order=selected_order,
        selected_market=selected_market,
        order_profit=order_profit,
        market_profit=market_profit,
    )
