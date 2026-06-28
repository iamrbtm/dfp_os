from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from app.extensions import db
from app.models import (
    CostSnapshot,
    Expense,
    FilamentSpool,
    Order,
    PaymentMethod,
    PosSale,
    PrintJob,
    PrintJobStatus,
    Printer,
    PrinterStatus,
    Product,
)
from app.services.settings import get_setting


CENT = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
COST_FORMULA_VERSION = "2026-06-26.product-studio-v1"


def money(value: Decimal | int | str | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def decimal4(value: Decimal | int | str | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class CostBreakdown:
    material_cost: Decimal
    filament_grams: Decimal
    cost_per_gram: Decimal
    labor_minutes: Decimal
    labor_rate: Decimal
    labor_cost: Decimal
    print_minutes: Decimal
    machine_hour_rate: Decimal
    machine_cost: Decimal
    packaging_cost: Decimal
    payment_fees: Decimal
    market_allocation: Decimal
    failure_rate: Decimal
    failure_adjustment: Decimal
    total_cost: Decimal
    suggested_price: Decimal
    margin_dollars: Decimal
    margin_percent: Decimal
    evidence_source: str
    confidence: str
    formula_version: str
    printer_model: str | None
    selected_spool_id: int | None
    model_volume_cm3: Decimal
    profit_per_unit: Decimal
    profit_per_print_hour: Decimal
    profit_per_market_bin_cm3: Decimal
    snapshot_id: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_dict_str(self) -> dict[str, str | None]:
        return {key: _serialize_value(value) for key, value in self.as_dict().items()}


def _serialize_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _decimal_setting(key: str, default: str) -> Decimal:
    return Decimal(str(get_setting(key, default) or default))


def _cost_settings() -> dict[str, Decimal]:
    energy = _decimal_setting("cost_engine_energy_hour_rate", "0.18")
    depreciation = _decimal_setting("cost_engine_depreciation_hour_rate", "0.22")
    maintenance = _decimal_setting("cost_engine_maintenance_hour_rate", "0.06")
    ams_waste = _decimal_setting("cost_engine_ams_waste_hour_rate", "0.04")
    return {
        "labor_rate": _decimal_setting("cost_engine_labor_rate", "18.00"),
        "packaging_cost": _decimal_setting("cost_engine_packaging_cost", "0.50"),
        "failure_rate": _decimal_setting("cost_engine_failure_rate", "0.05"),
        "target_margin_percent": _decimal_setting("cost_engine_target_margin_percent", "55.00"),
        "machine_hour_rate": money(energy + depreciation + maintenance + ams_waste),
    }


def _latest_model_analysis(product: Product) -> dict[str, object] | None:
    if (
        product.analysis_status != "complete"
        or product.parsed_filament_grams is None
        or product.parsed_print_minutes is None
    ):
        return None

    volume_cm3 = Decimal("0.00")
    if product.parsed_volume_mm3 is not None:
        volume_cm3 = decimal4(Decimal(str(product.parsed_volume_mm3)) / Decimal("1000"))

    return {
        "filament_grams": Decimal(str(product.parsed_filament_grams or 0)),
        "print_minutes": Decimal(str(product.parsed_print_minutes or 0)),
        "model_volume_cm3": volume_cm3,
        "evidence_source": "generated_slice.product",
    }


def _best_spool_match() -> tuple[Decimal, int | None]:
    query = FilamentSpool.query.filter(
        FilamentSpool.remaining_weight_grams > 0,
        FilamentSpool.cost_per_gram > 0,
    )
    candidates = query.all()
    if not candidates:
        return Decimal("0.0000"), None

    total_grams = sum(Decimal(str(candidate.remaining_weight_grams or 0)) for candidate in candidates)
    if total_grams <= 0:
        return Decimal("0.0000"), None

    weighted_cost = sum(
        Decimal(str(candidate.remaining_weight_grams or 0))
        * Decimal(str(candidate.cost_per_gram or 0))
        for candidate in candidates
    )
    latest = max(candidates, key=lambda candidate: candidate.updated_at or candidate.created_at)
    return decimal4(weighted_cost / total_grams), latest.id


def _count_jobs(
    *,
    product_id: int | None = None,
    printer_model: str | None = None,
    statuses: tuple[PrintJobStatus, ...],
) -> int:
    query = PrintJob.query
    if product_id is not None:
        query = query.filter(PrintJob.product_id == product_id)
    if printer_model:
        query = query.join(Printer, PrintJob.printer_id == Printer.id).filter(Printer.model == printer_model)
    return query.filter(PrintJob.status.in_(statuses)).count()


def _resolve_failure_rate(
    *,
    product: Product,
    printer_model: str | None,
    default_failure_rate: Decimal,
) -> Decimal:
    completed = _count_jobs(
        product_id=product.id,
        printer_model=printer_model,
        statuses=(PrintJobStatus.COMPLETED,),
    )
    failed = _count_jobs(
        product_id=product.id,
        printer_model=printer_model,
        statuses=(PrintJobStatus.FAILED,),
    )
    total = completed + failed
    if total > 0:
        return decimal4(Decimal(str(failed)) / Decimal(str(total)))
    return decimal4(default_failure_rate)


def _safe_rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (numerator / denominator).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_product_cost(
    *,
    product: Product,
    sale_price: Decimal | None = None,
    labor_rate: Decimal | None = None,
    packaging_cost: Decimal | None = None,
    machine_hour_rate: Decimal | None = None,
    payment_fee_rate: Decimal = Decimal("0.00"),
    market_allocation: Decimal = Decimal("0.00"),
    failure_rate: Decimal | None = None,
    target_margin_percent: Decimal | None = None,
    printer_model: str | None = None,
) -> CostBreakdown:
    settings = _cost_settings()
    labor_minutes = Decimal(str(product.estimated_labor_minutes or 0))
    labor_rate = Decimal(str(labor_rate if labor_rate is not None else settings["labor_rate"]))
    packaging_cost = money(packaging_cost if packaging_cost is not None else settings["packaging_cost"])
    machine_hour_rate = Decimal(
        str(machine_hour_rate if machine_hour_rate is not None else settings["machine_hour_rate"])
    )
    target_margin_percent = Decimal(
        str(target_margin_percent if target_margin_percent is not None else settings["target_margin_percent"])
    )

    resolved_cost_per_gram, selected_spool_id = _best_spool_match()
    model_data = _latest_model_analysis(product)
    if model_data is None:
        filament_grams = Decimal("0.00")
        print_minutes = Decimal("0.00")
        model_volume_cm3 = Decimal("0.00")
        material_cost = Decimal("0.00")
        machine_cost = Decimal("0.00")
        evidence_source = "no_model"
        confidence = "none"
        resolved_failure_rate = Decimal("0.0000")
        failure_adjustment = Decimal("0.00")
    else:
        filament_grams = decimal4(model_data["filament_grams"])
        print_minutes = decimal4(model_data["print_minutes"])
        model_volume_cm3 = decimal4(model_data["model_volume_cm3"])
        material_cost = money(filament_grams * resolved_cost_per_gram)
        machine_cost = money((print_minutes / Decimal("60")) * machine_hour_rate)
        evidence_source = str(model_data["evidence_source"])
        resolved_failure_rate = _resolve_failure_rate(
            product=product,
            printer_model=printer_model,
            default_failure_rate=Decimal(
                str(failure_rate if failure_rate is not None else settings["failure_rate"])
            ),
        )
        confidence = "high" if selected_spool_id is not None and resolved_failure_rate > Decimal("0") else "medium"
        if selected_spool_id is None:
            confidence = "low"

    labor_cost = money((labor_minutes / Decimal("60")) * labor_rate)
    base_cost = money(material_cost + labor_cost + machine_cost + packaging_cost + market_allocation)
    if model_data is None:
        failure_adjustment = Decimal("0.00")
    else:
        failure_adjustment = money(base_cost * resolved_failure_rate)

    price = money(sale_price if sale_price is not None else product.base_price)
    payment_fees = money(price * payment_fee_rate)
    total_cost = money(base_cost + failure_adjustment + payment_fees)

    divisor = Decimal("1.00") - (target_margin_percent / Decimal("100"))
    suggested_price = money(total_cost / divisor) if divisor > 0 else total_cost
    price_for_margin = price if price > Decimal("0.00") else suggested_price
    margin_dollars = money(price_for_margin - total_cost)
    margin_percent = Decimal("0.00")
    if price_for_margin > 0:
        margin_percent = ((margin_dollars / price_for_margin) * Decimal("100")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )

    profit_per_print_hour = Decimal("0.00")
    if print_minutes > 0:
        profit_per_print_hour = _safe_rate(margin_dollars, print_minutes / Decimal("60"))

    profit_per_market_bin_cm3 = Decimal("0.00")
    if model_volume_cm3 > 0:
        profit_per_market_bin_cm3 = _safe_rate(margin_dollars, model_volume_cm3)

    return CostBreakdown(
        material_cost=material_cost,
        filament_grams=filament_grams,
        cost_per_gram=resolved_cost_per_gram,
        labor_minutes=labor_minutes,
        labor_rate=labor_rate,
        labor_cost=labor_cost,
        print_minutes=print_minutes,
        machine_hour_rate=machine_hour_rate,
        machine_cost=machine_cost,
        packaging_cost=packaging_cost,
        payment_fees=payment_fees,
        market_allocation=money(market_allocation),
        failure_rate=resolved_failure_rate,
        failure_adjustment=failure_adjustment,
        total_cost=total_cost,
        suggested_price=suggested_price,
        margin_dollars=margin_dollars,
        margin_percent=margin_percent,
        evidence_source=evidence_source,
        confidence=confidence,
        formula_version=COST_FORMULA_VERSION,
        printer_model=printer_model,
        selected_spool_id=selected_spool_id,
        model_volume_cm3=model_volume_cm3,
        profit_per_unit=margin_dollars,
        profit_per_print_hour=profit_per_print_hour,
        profit_per_market_bin_cm3=profit_per_market_bin_cm3,
    )


def persist_cost_snapshot(
    *,
    product: Product,
    breakdown: CostBreakdown,
    snapshot_reason: str | None = None,
) -> CostSnapshot:
    CostSnapshot.query.filter(
        CostSnapshot.product_id == product.id,
        CostSnapshot.stale.is_(False),
    ).update({"stale": True}, synchronize_session=False)

    inputs = {
        "product_id": product.id,
        "price": _serialize_value(product.base_price),
        "estimated_labor_minutes": str(product.estimated_labor_minutes or 0),
        "printer_model": breakdown.printer_model,
        "formula_version": breakdown.formula_version,
    }
    outputs = breakdown.as_dict_str()

    snapshot = CostSnapshot(
        product_id=product.id,
        filament_spool_id=breakdown.selected_spool_id,
        formula_version=breakdown.formula_version,
        evidence_source=breakdown.evidence_source,
        confidence=breakdown.confidence,
        snapshot_reason=snapshot_reason,
        printer_model=breakdown.printer_model,
        stale=False,
        inputs_json=json.dumps(inputs, sort_keys=True),
        outputs_json=json.dumps(outputs, sort_keys=True),
    )
    db.session.add(snapshot)
    db.session.flush()
    breakdown.snapshot_id = snapshot.id
    return snapshot


def build_pricing_scenarios(
    *,
    product: Product,
    sale_price: Decimal | None = None,
) -> list[dict[str, str | bool | None]]:
    printer_models = [
        row[0]
        for row in db.session.query(Printer.model)
        .filter(
            Printer.status.in_(
                [
                    PrinterStatus.ACTIVE,
                    PrinterStatus.IDLE,
                    PrinterStatus.PRINTING,
                    PrinterStatus.MAINTENANCE,
                ]
            )
        )
        .distinct()
        .order_by(Printer.model.asc())
        .all()
        if row[0]
    ]

    scenarios: list[tuple[CostBreakdown, dict[str, str | bool | None]]] = []
    for model in printer_models or [None]:
        breakdown = calculate_product_cost(
            product=product,
            sale_price=sale_price,
            printer_model=model,
        )
        scenarios.append(
            (
                breakdown,
                {
                    "printer_model": model or "unassigned",
                    "margin_dollars": str(breakdown.margin_dollars),
                    "margin_percent": str(breakdown.margin_percent),
                    "profit_per_print_hour": str(breakdown.profit_per_print_hour),
                    "profit_per_market_bin_cm3": str(breakdown.profit_per_market_bin_cm3),
                    "failure_rate": str(breakdown.failure_rate),
                    "total_cost": str(breakdown.total_cost),
                    "confidence": breakdown.confidence,
                    "evidence_source": breakdown.evidence_source,
                    "recommended": False,
                },
            )
        )

    scenarios.sort(
        key=lambda item: (
            Decimal(str(item[1]["profit_per_print_hour"] or "0")),
            Decimal(str(item[1]["margin_dollars"] or "0")),
        ),
        reverse=True,
    )
    if scenarios:
        scenarios[0][1]["recommended"] = True
    return [scenario for _, scenario in scenarios]


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
            sale_price=item.unit_price,
        )
        total_cost += breakdown.total_cost * Decimal(str(item.quantity))
    profit = money(order.total - total_cost)
    margin = Decimal("0.00")
    if order.total:
        margin = ((profit / order.total) * Decimal("100")).quantize(CENT)
    return {"revenue": money(order.total), "cost": money(total_cost), "profit": profit, "margin_percent": margin}


def estimate_pos_sale_profit(sale_id: int) -> dict[str, Decimal]:
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        raise ValueError("POS sale not found")
    if sale.order_id:
        result = estimate_order_profit(sale.order_id)
    else:
        result = {
            "revenue": money(sale.total),
            "cost": Decimal("0.00"),
            "profit": money(sale.total),
            "margin_percent": Decimal("100.00"),
        }
    if sale.payment_method == PaymentMethod.CARD_EXTERNAL.value:
        fee = money(sale.total * Decimal("0.029") + Decimal("0.30"))
        result["cost"] = money(result["cost"] + fee)
        result["profit"] = money(result["profit"] - fee)
    return result


def estimate_market_profit(market_id: int) -> dict[str, Decimal]:
    revenue = (
        db.session.query(func.coalesce(func.sum(Order.total), 0))
        .filter(
            Order.market_id == market_id,
            Order.deleted_at.is_(None),
        )
        .scalar()
        or Decimal("0.00")
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.related_market_id == market_id)
        .scalar()
        or Decimal("0.00")
    )
    item_cost = Decimal("0.00")
    orders = Order.query.filter(Order.market_id == market_id, Order.deleted_at.is_(None)).all()
    for order in orders:
        item_cost += estimate_order_profit(order.id)["cost"]
    profit = money(revenue - expenses - item_cost)
    margin = Decimal("0.00")
    if revenue:
        margin = ((profit / revenue) * Decimal("100")).quantize(CENT)
    return {
        "revenue": money(revenue),
        "item_cost": money(item_cost),
        "expenses": money(expenses),
        "profit": profit,
        "margin_percent": margin,
    }
