from __future__ import annotations

from decimal import Decimal

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import Product, ProductVariant
from app.services.cost_engine import calculate_product_cost


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def calculate_product_cost_task(self, product_id: int) -> dict:
    product = db.session.get(Product, product_id)
    if product is None:
        return {"success": False, "error": "Product not found"}

    try:
        cost_per_gram = Decimal("0.025")
        labor_rate = Decimal("18.00")
        packaging_cost = Decimal("0.50")
        machine_hour_rate = Decimal("0.50")
        failure_rate = Decimal("0.05")
        target_margin = Decimal("55.00")

        try:
            from app.services.settings import get_setting
            cost_per_gram = Decimal(str(get_setting("cost_engine_cost_per_gram", "0.025")))
            labor_rate = Decimal(str(get_setting("cost_engine_labor_rate", "18.00")))
            packaging_cost = Decimal(str(get_setting("cost_engine_packaging_cost", "0.50")))
            machine_hour_rate = Decimal(str(get_setting("cost_engine_machine_hour_rate", "0.50")))
            failure_rate = Decimal(str(get_setting("cost_engine_failure_rate", "0.05")))
            target_margin = Decimal(str(get_setting("cost_engine_target_margin_percent", "55.00")))
        except Exception:
            pass

        breakdown = calculate_product_cost(
            product=product,
            variant=None,
            cost_per_gram=cost_per_gram,
            labor_rate=labor_rate,
            packaging_cost=packaging_cost,
            machine_hour_rate=machine_hour_rate,
            failure_rate=failure_rate,
            target_margin_percent=target_margin,
        )

        product.estimated_material_cost = breakdown.material_cost
        product.estimated_profit = breakdown.margin_dollars
        db.session.commit()

        variant_results = []
        for variant in product.variants:
            v_breakdown = calculate_product_cost(
                product=product,
                variant=variant,
                sale_price=variant.price,
                cost_per_gram=cost_per_gram,
                labor_rate=labor_rate,
                packaging_cost=packaging_cost,
                machine_hour_rate=machine_hour_rate,
                failure_rate=failure_rate,
                target_margin_percent=target_margin,
            )
            variant.material_cost = v_breakdown.material_cost
            variant.estimated_filament_grams = int(round(float(v_breakdown.filament_grams)))
            variant.estimated_print_minutes = int(round(float(v_breakdown.print_minutes)))
            db.session.commit()
            variant_results.append({
                "variant_id": variant.id,
                "total_cost": str(v_breakdown.total_cost),
                "margin_percent": str(v_breakdown.margin_percent),
            })

        return {
            "success": True,
            "product_id": product.id,
            "breakdown": breakdown.as_dict_str() if hasattr(breakdown, "as_dict_str") else str(breakdown),
            "variant_results": variant_results,
        }

    except Exception as exc:
        raise calculate_product_cost_task.retry(exc=exc)


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def calculate_variant_cost_task(self, variant_id: int) -> dict:
    variant = db.session.get(ProductVariant, variant_id)
    if variant is None:
        return {"success": False, "error": "Variant not found"}

    product = variant.product
    if product is None:
        return {"success": False, "error": "Variant has no product"}

    try:
        cost_per_gram = Decimal("0.025")
        labor_rate = Decimal("18.00")
        packaging_cost = Decimal("0.50")

        try:
            from app.services.settings import get_setting
            cost_per_gram = Decimal(str(get_setting("cost_engine_cost_per_gram", "0.025")))
            labor_rate = Decimal(str(get_setting("cost_engine_labor_rate", "18.00")))
            packaging_cost = Decimal(str(get_setting("cost_engine_packaging_cost", "0.50")))
        except Exception:
            pass

        breakdown = calculate_product_cost(
            product=product,
            variant=variant,
            sale_price=variant.price,
            cost_per_gram=cost_per_gram,
            labor_rate=labor_rate,
            packaging_cost=packaging_cost,
        )

        variant.material_cost = breakdown.material_cost
        variant.estimated_filament_grams = int(round(float(breakdown.filament_grams)))
        variant.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        db.session.commit()

        return {
            "success": True,
            "variant_id": variant.id,
            "total_cost": str(breakdown.total_cost),
            "suggested_price": str(breakdown.suggested_price),
            "margin_percent": str(breakdown.margin_percent),
            "material_cost": str(breakdown.material_cost),
            "filament_grams": str(breakdown.filament_grams),
            "print_minutes": str(breakdown.print_minutes),
        }

    except Exception as exc:
        raise calculate_variant_cost_task.retry(exc=exc)
