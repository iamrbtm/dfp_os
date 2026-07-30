from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app
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
COST_FORMULA_VERSION = "1.0.0"


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
        "payment_fee_rate": _decimal_setting("cost_engine_payment_fee_rate", "0.029"),
        "market_allocation": _decimal_setting("cost_engine_market_allocation", "0.00"),
        "machine_hour_rate": money(energy + depreciation + maintenance + ams_waste),
    }


def global_cost_defaults() -> dict[str, str]:
    """Return the global cost-engine defaults as display strings (Issue 14).

    The Product Studio Cost Inputs section shows each global default next to its
    override field so the user knows what value is assumed when they leave the
    override blank.
    """
    settings = _cost_settings()
    return {
        "labor_rate": str(settings["labor_rate"]),
        "packaging_cost": str(settings["packaging_cost"]),
        "target_margin_percent": str(settings["target_margin_percent"]),
        "failure_rate": str(settings["failure_rate"]),
        "machine_hour_rate": str(settings["machine_hour_rate"]),
        "payment_fee_rate": str(settings["payment_fee_rate"]),
        "market_allocation": str(settings["market_allocation"]),
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


@dataclass
class CostResolverResult:
    """Outcome of resolving a filament cost for a product (Issues 13, 25, 47).

    ``cost_per_gram`` is the resolved price to apply. ``spool_id`` is the
    primary spool behind the resolution (the exact spool when one is selected,
    otherwise the most-recently-updated spool in the matched set, or ``None``
    when no spools exist). ``confidence`` follows the Issue 25 rules and never
    depends on the print failure rate. ``evidence`` records how the value was
    derived for audit/debugging.
    """

    cost_per_gram: Decimal
    spool_id: int | None
    confidence: str
    evidence: dict = field(default_factory=dict)


def _spool_sort_key(spool: FilamentSpool):
    return spool.updated_at or spool.created_at


def _weighted_average(spoons: list[FilamentSpool]) -> Decimal:
    total_grams = sum(Decimal(str(s.remaining_weight_grams or 0)) for s in spoons)
    if total_grams <= 0:
        return Decimal("0.0000")
    weighted = sum(
        Decimal(str(s.remaining_weight_grams or 0)) * Decimal(str(s.cost_per_gram or 0))
        for s in spoons
    )
    return decimal4(weighted / total_grams)


def resolve_material_cost(
    business_id: int | None,
    material_type: str | None,
    *,
    color: str | None = None,
    spool_id: int | None = None,
    fallback_policy: str = "business_material",
) -> CostResolverResult:
    """Resolve a cost-per-gram for a product's filament (Issues 13, 25, 47).

    Matching priority:

    (a) ``spool_id`` given and exists and matches ``business_id`` (or
        ``business_id`` is None) -> use that spool's cost, confidence "high".
    (b) same business + same ``material_type`` (color optional refinement) ->
        weighted-average ``cost_per_gram`` by ``remaining_weight_grams`` across
        matched spools, confidence "high".
    (c) same business, no material match -> fallback average across that
        business's spools, confidence "medium", evidence["fallback_reason"]
        = "no_material_match".
    (d) no spools at all -> cost_per_gram=0, confidence "none",
        evidence["fallback_reason"] = "no_spools".

    When ``business_id`` is not None, every query is filtered to that business
    (cross-business isolation is the core fix of Issue 13). Only spools with
    remaining weight and a positive cost are considered for averaging.
    """
    base_query = FilamentSpool.query.filter(
        FilamentSpool.remaining_weight_grams > 0,
        FilamentSpool.cost_per_gram > 0,
    )
    if business_id is not None:
        base_query = base_query.filter(FilamentSpool.business_id == business_id)

    # (a) explicit spool selection.
    if spool_id is not None:
        spool = db.session.get(FilamentSpool, spool_id)
        if spool is not None and (business_id is None or spool.business_id == business_id):
            return CostResolverResult(
                cost_per_gram=decimal4(spool.cost_per_gram),
                spool_id=spool.id,
                confidence="high",
                evidence={
                    "matched_spool_ids": [spool.id],
                    "weighted_average": False,
                    "match_type": "spool_id",
                },
            )

    # (b) same business + same material_type (color optional refinement).
    material_query = base_query
    if material_type is not None:
        material_query = material_query.filter(
            FilamentSpool.material_type.ilike(material_type)
        )
    if color is not None:
        material_query = material_query.filter(FilamentSpool.color_name.ilike(color))
    matched = material_query.all()
    if matched:
        return CostResolverResult(
            cost_per_gram=_weighted_average(matched),
            spool_id=max(matched, key=_spool_sort_key).id,
            confidence="high",
            evidence={
                "matched_spool_ids": [s.id for s in matched],
                "weighted_average": True,
                "match_type": "material",
                "business_id": business_id,
                "material_type": material_type,
            },
        )

    # (c) fallback average across the business's spools (no material match).
    # When business_id is None this averages across every spool globally.
    fallback_query = base_query
    fallback = fallback_query.all()
    if fallback:
        return CostResolverResult(
            cost_per_gram=_weighted_average(fallback),
            spool_id=max(fallback, key=_spool_sort_key).id,
            confidence="medium",
            evidence={
                "matched_spool_ids": [s.id for s in fallback],
                "weighted_average": True,
                "match_type": "fallback",
                "business_id": business_id,
                "fallback_reason": "no_material_match",
                "fallback_policy": fallback_policy,
            },
        )

    # (d) no spools at all.
    return CostResolverResult(
        cost_per_gram=Decimal("0.0000"),
        spool_id=None,
        confidence="none",
        evidence={
            "matched_spool_ids": [],
            "weighted_average": False,
            "match_type": "none",
            "business_id": business_id,
            "fallback_reason": "no_spools",
            "fallback_policy": fallback_policy,
        },
    )


def _best_spool_match() -> tuple[Decimal, int | None]:
    """Backward-compatible global weighted average (Issue 13).

    Existing callers (app/tasks/model_analysis.py) expect a global
    weighted-average cost and the most-recent spool id. This is a thin wrapper
    around :func:`resolve_material_cost` with no business or material filter so
    pre-existing behavior is preserved.
    """
    result = resolve_material_cost(business_id=None, material_type=None)
    return result.cost_per_gram, result.spool_id


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
    if printer_model:
        from app.services.printer_reliability import get_failure_rate_for_cost_engine

        model_rate = get_failure_rate_for_cost_engine(printer_model=printer_model)
        if model_rate is not None:
            return decimal4(model_rate)
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
    payment_fee_rate: Decimal | None = None,
    market_allocation: Decimal | None = None,
    failure_rate: Decimal | None = None,
    target_margin_percent: Decimal | None = None,
    printer_model: str | None = None,
) -> CostBreakdown:
    settings = _cost_settings()
    labor_minutes = Decimal(str(product.estimated_labor_minutes or 0))
    labor_rate = Decimal(str(labor_rate if labor_rate is not None else settings["labor_rate"]))
    # Issue 14 — packaging_cost reads the product override when the caller does
    # not supply one, mirroring the market/payment override pattern below.
    if packaging_cost is None:
        packaging_cost = getattr(product, "packaging_cost_override", None)
    packaging_cost = money(packaging_cost if packaging_cost is not None else settings["packaging_cost"])
    machine_hour_rate = Decimal(
        str(machine_hour_rate if machine_hour_rate is not None else settings["machine_hour_rate"])
    )
    # Issue 14 — target_margin_percent reads the product override when the
    # caller does not supply one, mirroring the market/payment override pattern.
    if target_margin_percent is None:
        target_margin_percent = getattr(product, "target_margin_percent_override", None)
    target_margin_percent = Decimal(
        str(target_margin_percent if target_margin_percent is not None else settings["target_margin_percent"])
    )

    # Issue 38 — product-level overrides. The caller may pass None to mean "use
    # the product's configured override if one exists, else the global default
    # from Settings". The override columns are added by the integrator later;
    # getattr keeps this working whether or not they exist yet.
    if payment_fee_rate is None:
        payment_fee_rate = getattr(product, "payment_fee_rate_override", None)
    if payment_fee_rate is None:
        payment_fee_rate = settings["payment_fee_rate"]
    payment_fee_rate = Decimal(str(payment_fee_rate))
    if market_allocation is None:
        market_allocation = getattr(product, "market_allocation_override", None)
    if market_allocation is None:
        market_allocation = settings["market_allocation"]
    market_allocation = Decimal(str(market_allocation))

    # Issue 25 — resolve filament cost from the product's business + material.
    # Issue 14 — prefer the product's configured spool override when present.
    material_type: str | None = None
    analysis_config = product.model_analysis_config or {}
    if isinstance(analysis_config, dict):
        material_type = analysis_config.get("material")
    preferred_spool_id = getattr(product, "material_spool_override", None)
    resolver = resolve_material_cost(
        business_id=product.business_id,
        material_type=material_type,
        spool_id=preferred_spool_id,
    )
    resolved_cost_per_gram = resolver.cost_per_gram
    selected_spool_id = resolver.spool_id
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
        # Issue 25 — confidence comes from the resolver and never depends on
        # the failure rate. cost_per_gram == 0 means no spool cost data.
        if resolved_cost_per_gram <= 0:
            evidence_source = "no_spool_cost"
            confidence = "none"
        else:
            evidence_source = str(model_data["evidence_source"])
            confidence = resolver.confidence
        resolved_failure_rate = _resolve_failure_rate(
            product=product,
            printer_model=printer_model,
            default_failure_rate=Decimal(
                str(failure_rate if failure_rate is not None else settings["failure_rate"])
            ),
        )

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
    analysis_run_id: int | None = None,
    model_asset_id: int | None = None,
    file_sha256: str | None = None,
    slicer_settings_hash: str | None = None,
    material: str | None = None,
    density: Decimal | None = None,
    density_source: str | None = None,
    scale_percent: int | None = None,
    copies: int | None = None,
    cost_resolver_evidence: dict | None = None,
    actor_id: int | None = None,
    before_snapshot_id: int | None = None,
    audit_client=None,
) -> CostSnapshot:
    """Persist one cost snapshot with full evidence (Issues 15, 26, 17).

    Acquires a row lock on the product so two concurrent calculations cannot
    both create a "current" snapshot. Within the same transaction the prior
    current snapshot is marked stale, the new one inserted, then the caller
    commits to release the lock. The new snapshot always links to a model
    asset / analysis run when one is available (Issue 15).

    Issue 17 — an optional audit hook fires when ``audit_client`` is supplied
    or when the app-level audit client is enabled via ``AUDIT_LOG_ENABLED``.
    A missing/unavailable audit service never breaks snapshot creation.
    """
    # Issue 26 — SELECT ... FOR UPDATE on the product row.
    db.session.query(Product).filter(Product.id == product.id).with_for_update().first()

    db.session.query(CostSnapshot).filter(
        CostSnapshot.product_id == product.id,
        CostSnapshot.stale.is_(False),
    ).update({CostSnapshot.stale: True}, synchronize_session=False)

    inputs = {
        "product_id": product.id,
        "price": _serialize_value(product.base_price),
        "estimated_labor_minutes": str(product.estimated_labor_minutes or 0),
        "printer_model": breakdown.printer_model,
        "formula_version": breakdown.formula_version,
        "material": material,
        "density": _serialize_value(density),
        "density_source": density_source,
        "scale_percent": scale_percent,
        "copies": copies,
        "analysis_run_id": analysis_run_id,
        "model_asset_id": model_asset_id,
    }
    outputs = breakdown.as_dict_str()

    snapshot = CostSnapshot(
        product_id=product.id,
        filament_spool_id=breakdown.selected_spool_id,
        model_asset_id=model_asset_id,
        analysis_run_id=analysis_run_id,
        formula_version=breakdown.formula_version,
        evidence_source=breakdown.evidence_source,
        confidence=breakdown.confidence,
        snapshot_reason=snapshot_reason,
        printer_model=breakdown.printer_model,
        stale=False,
        file_sha256=file_sha256,
        slicer_settings_hash=slicer_settings_hash,
        material=material,
        density=density,
        density_source=density_source,
        scale_percent=scale_percent,
        copies=copies,
        parsed_filament_grams=breakdown.filament_grams,
        parsed_print_minutes=breakdown.print_minutes,
        cost_resolver_evidence_json=(
            json.dumps(cost_resolver_evidence, sort_keys=True) if cost_resolver_evidence else None
        ),
        inputs_json=json.dumps(inputs, sort_keys=True),
        outputs_json=json.dumps(outputs, sort_keys=True),
    )
    db.session.add(snapshot)
    db.session.flush()
    breakdown.snapshot_id = snapshot.id

    # Issue 17 — best-effort audit event for the new snapshot.
    _record_snapshot_audit(
        snapshot=snapshot,
        breakdown=breakdown,
        analysis_run_id=analysis_run_id,
        actor_id=actor_id,
        before_snapshot_id=before_snapshot_id,
        audit_client=audit_client,
    )
    return snapshot


def _record_snapshot_audit(
    *,
    snapshot: CostSnapshot,
    breakdown: CostBreakdown,
    analysis_run_id: int | None,
    actor_id: int | None,
    before_snapshot_id: int | None = None,
    audit_client=None,
) -> None:
    """Fire a ``cost_snapshot.created`` audit event, swallowing errors (Issue 17)."""
    try:
        client = audit_client
        if client is None:
            if not current_app.config.get("AUDIT_LOG_ENABLED", False):
                return
            from app.services.audit_client import get_audit_client

            client = get_audit_client()

        # Issue 17 — record what the previous current snapshot was so the audit
        # trail shows the before→after transition, not just the after state.
        before_state = None
        if before_snapshot_id is not None:
            prior = db.session.get(CostSnapshot, before_snapshot_id)
            if prior is not None:
                prior_outputs = {}
                if prior.outputs_json:
                    try:
                        prior_outputs = json.loads(prior.outputs_json)
                    except (ValueError, TypeError):
                        prior_outputs = {}
                before_state = {
                    "snapshot_id": prior.id,
                    "confidence": prior.confidence,
                    "total_cost": prior_outputs.get("total_cost"),
                    "suggested_price": prior_outputs.get("suggested_price"),
                }
        client.record(
            action="cost_snapshot.created",
            entity_type="cost_snapshot",
            entity_id=str(snapshot.id),
            actor_id=str(actor_id) if actor_id is not None else None,
            actor_type="user" if actor_id is not None else "system",
            before_state=before_state,
            after_state={
                "snapshot_id": snapshot.id,
                "analysis_run_id": analysis_run_id,
                "confidence": breakdown.confidence,
                "formula_version": breakdown.formula_version,
            },
        )
    except Exception:  # noqa: BLE001 — audit must never break snapshot creation.
        current_app.logger.warning("cost_snapshot audit event failed for snapshot %s", snapshot.id)


def recalculate_snapshot(snapshot_id: int, *, snapshot_reason: str = "recalculate") -> CostSnapshot | None:
    """Re-run the current cost formula against an old snapshot (Issue 43).

    The old snapshot's identity/evidence is preserved; a fresh snapshot is
    written with the current ``COST_FORMULA_VERSION`` and the prior one is
    marked stale. Returns the new snapshot, or ``None`` if the input is gone.
    """
    original = db.session.get(CostSnapshot, snapshot_id)
    if original is None:
        return None
    product = db.session.get(Product, original.product_id)
    if product is None:
        return None
    breakdown = calculate_product_cost(
        product=product,
        printer_model=original.printer_model,
    )
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
    new_snapshot = persist_cost_snapshot(
        product=product,
        breakdown=breakdown,
        snapshot_reason=snapshot_reason,
        analysis_run_id=original.analysis_run_id,
        model_asset_id=original.model_asset_id,
        file_sha256=original.file_sha256,
        slicer_settings_hash=original.slicer_settings_hash,
        material=original.material,
        density=original.density,
        density_source=original.density_source,
        scale_percent=original.scale_percent,
        copies=original.copies,
    )
    return new_snapshot


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
