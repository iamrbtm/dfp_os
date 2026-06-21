from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Category,
    FeatureFlag,
    InventoryLocation,
    InventoryMovement,
    InventoryRecord,
    Market,
    MarketStatus,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
)
from app.services.cost_engine import calculate_product_cost
from app.services.inventory import deduct_finished_goods
from app.services.prep_tasks import generate_market_prep_tasks, market_readiness_score


def _product_with_variant():
    category = Category(name="Foundation", slug="foundation", is_public=False)
    product = Product(
        name="Foundation Dragon",
        slug="foundation-dragon",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        base_price=Decimal("20.00"),
        estimated_material_cost=Decimal("3.00"),
        estimated_labor_minutes=10,
        estimated_print_minutes=120,
    )
    variant = ProductVariant(
        product=product,
        sku="FOUND-DRG-001",
        name="Default",
        price=Decimal("20.00"),
        material_cost=Decimal("3.00"),
        estimated_filament_grams=100,
        estimated_print_minutes=120,
        active=True,
    )
    db.session.add_all([category, product, variant])
    db.session.flush()
    return product, variant


def test_disabled_module_blocks_route(client, login_admin):
    with client.application.app_context():
        db.session.add(FeatureFlag(key="module.pos.enabled", enabled=False))
        db.session.commit()

    response = client.get("/pos/sessions", follow_redirects=False)
    assert response.status_code == 403


def test_disabled_module_blocks_api(client, api_token):
    with client.application.app_context():
        db.session.add(FeatureFlag(key="module.pos.enabled", enabled=False))
        db.session.commit()

    response = client.get("/api/v1/pos-sessions", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "module_disabled"


def test_inventory_deduction_records_movement(app):
    with app.app_context():
        product, variant = _product_with_variant()
        location = InventoryLocation(name="Foundation Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        record = InventoryRecord(
            product_id=product.id,
            variant_id=variant.id,
            location_id=location.id,
            quantity_on_hand=5,
        )
        db.session.add(record)
        db.session.commit()

        result = deduct_finished_goods(
            product_id=product.id,
            variant_id=variant.id,
            quantity=2,
            location_id=location.id,
            reference_type="test",
            reference_id="abc",
        )
        db.session.commit()

        assert result.deducted == 2
        assert record.quantity_on_hand == 3
        assert InventoryMovement.query.count() == 1


def test_inventory_deduction_blocks_negative(app):
    with app.app_context():
        product, variant = _product_with_variant()
        location = InventoryLocation(name="No Negative Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        record = InventoryRecord(
            product_id=product.id,
            variant_id=variant.id,
            location_id=location.id,
            quantity_on_hand=1,
        )
        db.session.add(record)
        db.session.commit()

        with pytest.raises(ValueError, match="Insufficient inventory"):
            deduct_finished_goods(
                product_id=product.id,
                variant_id=variant.id,
                quantity=2,
                location_id=location.id,
                reference_type="test",
                reference_id="abc",
            )


def test_cost_engine_product_breakdown(app):
    with app.app_context():
        product, variant = _product_with_variant()
        breakdown = calculate_product_cost(product=product, variant=variant)
        assert breakdown.total_cost > Decimal("0")
        assert breakdown.margin_dollars > Decimal("0")
        assert breakdown.suggested_price > breakdown.total_cost


def test_market_prep_generation(app):
    with app.app_context():
        product, variant = _product_with_variant()
        location = InventoryLocation(name="Prep Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                variant_id=variant.id,
                location_id=location.id,
                quantity_on_hand=0,
            )
        )
        market = Market(
            name="Foundation Market",
            event_date=date(2026, 7, 1),
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()

        tasks = generate_market_prep_tasks(market.id)
        readiness = market_readiness_score(market.id)

        assert len(tasks) >= 1
        assert readiness["total"] == len(tasks)
        assert readiness["score"] == Decimal("0.00")


def test_analytics_insights_fallback(app):
    with app.app_context():
        from app.services.analytics import analytics_insights

        result = analytics_insights()
        assert result["enabled"] is False
        assert "numbers" in result


def test_audit_dispatch_called_for_pos_session(app, monkeypatch):
    from app.models import User, UserRole
    from app.services.pos import open_session

    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        app.config["AUDIT_LOG_ENABLED"] = True
        app.config["AUDIT_LOG_BASE_URL"] = "http://audit.test"
        app.config["AUDIT_LOG_TOKEN"] = "token"
        user = User(
            email="audit-pos@example.com",
            first_name="Audit",
            last_name="POS",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        open_session(user_id=user.id, opening_cash=Decimal("25.00"))

    assert any(call["action"] == "pos_session.opened" for call in calls)
