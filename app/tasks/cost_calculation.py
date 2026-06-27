from __future__ import annotations

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import Product, ProductVariant
from app.services.cost_engine import calculate_product_cost, persist_cost_snapshot


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def calculate_product_cost_task(self, product_id: int) -> dict:
    product = db.session.get(Product, product_id)
    if product is None:
        return {"success": False, "error": "Product not found"}

    try:
        breakdown = calculate_product_cost(product=product)
        product.estimated_material_cost = breakdown.material_cost
        product.estimated_profit = breakdown.margin_dollars
        product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        persist_cost_snapshot(product=product, variant=None, breakdown=breakdown, snapshot_reason="task.product")

        variant_results = []
        for variant in product.variants:
            v_breakdown = calculate_product_cost(
                product=product,
                variant=variant,
                sale_price=variant.price,
            )
            variant.material_cost = v_breakdown.material_cost
            variant.estimated_filament_grams = int(round(float(v_breakdown.filament_grams)))
            variant.estimated_print_minutes = int(round(float(v_breakdown.print_minutes)))
            persist_cost_snapshot(
                product=product,
                variant=variant,
                breakdown=v_breakdown,
                snapshot_reason="task.variant",
            )
            variant_results.append({
                "variant_id": variant.id,
                "total_cost": str(v_breakdown.total_cost),
                "margin_percent": str(v_breakdown.margin_percent),
                "snapshot_id": v_breakdown.snapshot_id,
            })

        db.session.commit()
        return {
            "success": True,
            "product_id": product.id,
            "breakdown": breakdown.as_dict_str(),
            "variant_results": variant_results,
        }

    except Exception as exc:
        db.session.rollback()
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
        breakdown = calculate_product_cost(
            product=product,
            variant=variant,
            sale_price=variant.price,
        )
        variant.material_cost = breakdown.material_cost
        variant.estimated_filament_grams = int(round(float(breakdown.filament_grams)))
        variant.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        persist_cost_snapshot(
            product=product,
            variant=variant,
            breakdown=breakdown,
            snapshot_reason="task.variant",
        )
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
            "snapshot_id": breakdown.snapshot_id,
        }

    except Exception as exc:
        db.session.rollback()
        raise calculate_variant_cost_task.retry(exc=exc)
