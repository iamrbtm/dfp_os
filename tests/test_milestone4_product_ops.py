from __future__ import annotations

from app.extensions import db
from app.models import (
    Category,
    DeadStockRecommendationStatus,
    InventoryLocation,
    InventoryRecord,
    LicenseStatus,
    Product,
    ProductPhotoShot,
    ProductStatus,
    ProductType,
)
from app.services.product_ops import (
    accept_dead_stock_recommendation,
    calculate_product_readiness,
    ensure_product_ops_defaults,
    generate_dead_stock_recommendation,
    launch_gate,
    update_photo_shot,
    update_story_card,
)


def _product(**overrides) -> Product:
    category = Category(name="Milestone Dragons", slug="milestone-dragons", is_public=True)
    data = {
        "name": "Launch Dragon",
        "slug": "launch-dragon",
        "sku_base": "M4-DRAGON",
        "short_description": "A shelf-ready dragon.",
        "description": "A shelf-ready articulated dragon for market tables.",
        "category": category,
        "product_type": ProductType.FINISHED_GOOD,
        "status": ProductStatus.DRAFT,
        "is_public": False,
        "is_pos_visible": True,
        "base_price": 24,
        "estimated_material_cost": 4,
        "estimated_profit": 18,
        "license_status": LicenseStatus.COMMERCIAL_ALLOWED,
        "model_commercial_use_allowed": True,
        "analysis_status": "complete",
        "care_instructions": "Keep away from high heat.",
        "safety_notes": "Small parts are not for very young children.",
    }
    data.update(overrides)
    product = Product(**data)
    db.session.add(product)
    db.session.flush()
    location = InventoryLocation(name=f"Market Bin {product.slug}", type="finished_goods")
    db.session.add(location)
    db.session.flush()
    db.session.add(
        InventoryRecord(
            product=product,
            location=location,
            quantity_on_hand=5,
            reorder_threshold=2,
            reorder_target=8,
        )
    )
    ensure_product_ops_defaults(product)
    db.session.commit()
    return product


def test_product_readiness_score_and_license_cap(app):
    with app.app_context():
        product = _product()
        shot = ProductPhotoShot.query.filter_by(product_id=product.id).first()
        assert shot is not None
        shot.completed = True
        db.session.commit()

        readiness = calculate_product_readiness(product)
        assert readiness.score >= 88
        assert not readiness.critical_blockers

        product.license_status = LicenseStatus.PERSONAL_ONLY
        product.model_commercial_use_allowed = False
        db.session.commit()

        capped = calculate_product_readiness(product)
        assert capped.score <= 45
        assert "Commercial rights need review." in capped.critical_blockers


def test_launch_gate_requires_override_for_critical_blockers(app):
    with app.app_context():
        product = _product(base_price=0)

        allowed, blockers = launch_gate(product)
        assert allowed is False
        assert "Base price is missing." in blockers

        product.launch_override_reason = "Owner approved market test."
        db.session.commit()

        allowed, blockers = launch_gate(product)
        assert allowed is True
        assert blockers == []


def test_product_story_card_public_rendering_and_photo_shot(client, app):
    with app.app_context():
        product = _product()
        shot = ProductPhotoShot.query.filter_by(product_id=product.id).first()
        update_photo_shot(
            shot,
            completed=True,
            image_reference="hero.jpg",
            notes="Shot on table.",
        )
        update_story_card(
            product,
            {
                "story_what_it_is": "A flexible dragon.",
                "story_who_it_is_for": "Market shoppers and gift buyers.",
                "story_materials": "PLA silk filament.",
                "story_customization_options": "Color can change.",
                "story_internal_compliance_notes": "Internal license proof link.",
            },
        )
        product_id = product.id
        product = db.session.get(Product, product_id)
        product.status = ProductStatus.ACTIVE
        product.is_public = True
        db.session.commit()

    public = client.get("/shop/launch-dragon")
    assert public.status_code == 200
    assert b"A flexible dragon." in public.data
    assert b"Market shoppers and gift buyers." in public.data
    assert b"Internal license proof link." not in public.data


def test_dead_stock_rescue_and_acceptance(app):
    with app.app_context():
        product = _product(
            name="Slow Turtle",
            slug="slow-turtle",
            sku_base="M4-TURTLE",
            is_public=False,
            is_pos_visible=False,
            estimated_profit=0,
        )
        product.inventory_records[0].quantity_on_hand = 12
        db.session.commit()

        recommendation = generate_dead_stock_recommendation(product)
        assert recommendation is not None
        assert recommendation.score >= 65
        assert "inventory has not sold yet" in recommendation.reason

        accept_dead_stock_recommendation(recommendation, notes="Bundle for next market.")
        assert recommendation.status == DeadStockRecommendationStatus.ACCEPTED
        assert recommendation.action_notes == "Bundle for next market."


def test_api_readiness_and_retirement(client, app, api_token):
    with app.app_context():
        product = _product(name="Retire Dragon", slug="retire-dragon", sku_base="M4-RETIRE")
        product_id = product.id

    headers = {"Authorization": f"Bearer {api_token}"}
    readiness = client.get(f"/api/v1/products/{product_id}/readiness", headers=headers)
    assert readiness.status_code == 200
    assert readiness.get_json()["data"]["score"] >= 80

    retired = client.post(
        f"/api/v1/products/{product_id}/retire",
        json={"reason": "Poor sell-through.", "discount_remaining": True},
        headers=headers,
    )
    assert retired.status_code == 200
    data = retired.get_json()
    assert data["status"] == "retired"
    assert data["is_public"] is False
    assert data["is_pos_visible"] is False
    assert data["block_reprint"] is True
