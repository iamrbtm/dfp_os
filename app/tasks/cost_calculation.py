from __future__ import annotations

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import Product
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
        persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="task.product")
        db.session.commit()
        return {
            "success": True,
            "product_id": product.id,
            "breakdown": breakdown.as_dict_str(),
        }
    except Exception as exc:
        db.session.rollback()
        raise calculate_product_cost_task.retry(exc=exc)
