from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from app.extensions import db
from app.models import Expense, Order, PaymentMethod, PosSale, Product, ProductVariant


CENT = Decimal("0.01")


def money(value: Decimal | int | str | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CostBreakdown:
    material_cost: Decimal
    filament_grams: Decimal
    cost_per_gram: Decimal
    labor_minutes: Decimal
    labor_rate: Decimal
    print_minutes: Decimal
    machine_cost: Decimal
    packaging_cost: Decimal
    payment_fees: Decimal
    market_allocation: Decimal
    failure_adjustment: Decimal
    total_cost: Decimal
    suggested_price: Decimal
    margin_dollars: Decimal
    margin_percent: Decimal

    def as_dict(self) -> dict[str, Decimal]:
        return self.__dict__.copy()


def _latest_model_analysis(product: Product, variant: ProductVariant | None = None) -> dict | None:
    if variant is not None:
        assets = [asset for asset in (getattr(variant, "model_assets", []) or []) if asset.variant_id == variant.id]
    else:
        assets = [asset for asset in (getattr(product, "model_assets", []) or []) if asset.variant_id is None]
    completed = [
        a for a in assets
        if a.analysis_status == "complete" and a.parsed_filament_grams
    ]
    if not completed:
        return None
    latest = max(completed, key=lambda a: a.analysis_completed_at or a.created_at)
    return {
        "filament_grams": Decimal(str(latest.parsed_filament_grams or 0)),
        "print_minutes": Decimal(str(latest.parsed_print_minutes or 0)),
    }


def calculate_product_cost(
    *,
    product: Product,
    variant: ProductVariant | None = None,
    sale_price: Decimal | None = None,
    cost_per_gram: Decimal | None = None,
    labor_rate: Decimal = Decimal("18.00"),
    packaging_cost: Decimal = Decimal("0.50"),
    machine_hour_rate: Decimal = Decimal("0.50"),
    payment_fee_rate: Decimal = Decimal("0.00"),
    market_allocation: Decimal = Decimal("0.00"),
    failure_rate: Decimal = Decimal("0.05"),
    target_margin_percent: Decimal = Decimal("55.00"),
) -> CostBreakdown:
    labor_minutes = Decimal(str(product.estimated_labor_minutes or 0))
    cost_per_gram = cost_per_gram if cost_per_gram is not None else Decimal("0.025")

    model_data = _latest_model_analysis(product, variant)
    if model_data:
        filament_grams = model_data["filament_grams"]
        print_minutes = model_data["print_minutes"]
        material_cost = money(filament_grams * cost_per_gram)
    else:
        filament_grams = Decimal("0")
        print_minutes = Decimal("0")
        material_cost = Decimal("0.00")

    labor_cost = money((labor_minutes / Decimal("60")) * labor_rate)
    machine_cost = money((print_minutes / Decimal("60")) * machine_hour_rate)
    base_cost = money(material_cost + labor_cost + machine_cost + packaging_cost + market_allocation)
    failure_adjustment = money(base_cost * failure_rate)

    price = money(sale_price if sale_price is not None else getattr(variant, "price", None) or product.base_price)
    payment_fees = money(price * payment_fee_rate)
    total_cost = money(base_cost + failure_adjustment + payment_fees)

    if price <= Decimal("0.00"):
        suggested_price = money(total_cost / (Decimal("1.00") - (target_margin_percent / Decimal("100"))))
        price_for_margin = suggested_price
    else:
        suggested_price = money(total_cost / (Decimal("1.00") - (target_margin_percent / Decimal("100"))))
        price_for_margin = price

    margin_dollars = money(price_for_margin - total_cost)
    margin_percent = Decimal("0.00")
    if price_for_margin > 0:
        margin_percent = ((margin_dollars / price_for_margin) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return CostBreakdown(
        material_cost=material_cost,
        filament_grams=filament_grams,
        cost_per_gram=cost_per_gram,
        labor_minutes=labor_minutes,
        labor_rate=labor_rate,
        print_minutes=print_minutes,
        machine_cost=machine_cost,
        packaging_cost=money(packaging_cost),
        payment_fees=payment_fees,
        market_allocation=money(market_allocation),
        failure_adjustment=failure_adjustment,
        total_cost=total_cost,
        suggested_price=suggested_price,
        margin_dollars=margin_dollars,
        margin_percent=margin_percent,
    )


def estimate_order_profit(order_id: int) -> dict[str, Decimal]:
    order = db.session.get(Order, order_id)
    if order is None:
        raise ValueError("Order not found")
    total_cost = Decimal("0.00")
    for item in order.items:
        if item.product is None:
            continue
        breakdown = calculate_product_cost(
            product=item.product,
            variant=item.variant,
            sale_price=item.unit_price,
        )
        total_cost += breakdown.total_cost * Decimal(str(item.quantity))
    profit = money(order.total - total_cost)
    margin = Decimal("0.00")
    if order.total:
        margin = ((profit / order.total) * Decimal("100")).quantize(Decimal("0.01"))
    return {"revenue": money(order.total), "cost": money(total_cost), "profit": profit, "margin_percent": margin}


def estimate_pos_sale_profit(sale_id: int) -> dict[str, Decimal]:
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        raise ValueError("POS sale not found")
    if sale.order_id:
        result = estimate_order_profit(sale.order_id)
    else:
        result = {"revenue": money(sale.total), "cost": Decimal("0.00"), "profit": money(sale.total), "margin_percent": Decimal("100.00")}
    if sale.payment_method == PaymentMethod.CARD_EXTERNAL.value:
        fee = money(sale.total * Decimal("0.029") + Decimal("0.30"))
        result["cost"] = money(result["cost"] + fee)
        result["profit"] = money(result["profit"] - fee)
    return result


def estimate_market_profit(market_id: int) -> dict[str, Decimal]:
    revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.market_id == market_id,
        Order.deleted_at.is_(None),
    ).scalar() or Decimal("0.00")
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.related_market_id == market_id,
    ).scalar() or Decimal("0.00")
    item_cost = Decimal("0.00")
    orders = Order.query.filter(Order.market_id == market_id, Order.deleted_at.is_(None)).all()
    for order in orders:
        item_cost += estimate_order_profit(order.id)["cost"]
    profit = money(revenue - expenses - item_cost)
    margin = Decimal("0.00")
    if revenue:
        margin = ((profit / revenue) * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "revenue": money(revenue),
        "item_cost": money(item_cost),
        "expenses": money(expenses),
        "profit": profit,
        "margin_percent": margin,
    }
