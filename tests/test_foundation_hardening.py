from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Category,
    CostSnapshot,
    FeatureFlag,
    FilamentSpool,
    InventoryLocation,
    InventoryMovement,
    InventoryRecord,
    Market,
    MarketStatus,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.cost_engine import calculate_product_cost
from app.services.inventory import deduct_finished_goods, release_inventory, reserve_inventory, transfer_inventory
from app.services.prep_tasks import generate_market_prep_tasks, market_readiness_score
from app.tasks.model_analysis import _apply_initial_cost_snapshot


def _product():
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
    db.session.add_all([category, product])
    db.session.flush()
    return product


def _add_spool(material_type: str = "PLA", cost_per_gram: Decimal = Decimal("0.0250")) -> FilamentSpool:
    spool = FilamentSpool(
        brand="Test Brand",
        material_type=material_type,
        color_name="Blue",
        spool_weight_grams=1000,
        remaining_weight_grams=1000,
        cost_per_spool=Decimal("25.00"),
        cost_per_gram=cost_per_gram,
    )
    db.session.add(spool)
    db.session.flush()
    return spool


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
        product = _product()
        location = InventoryLocation(name="Foundation Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        record = InventoryRecord(product_id=product.id, location_id=location.id, quantity_on_hand=5)
        db.session.add(record)
        db.session.commit()

        result = deduct_finished_goods(
            product_id=product.id,
            quantity=2,
            location_id=location.id,
            reference_type="test",
            reference_id="abc",
        )
        db.session.commit()

        assert result.deducted == 2
        assert record.quantity_on_hand == 3
        assert InventoryMovement.query.count() == 1


def test_inventory_transfer_and_reservation_flow(app):
    with app.app_context():
        product = _product()
        source = InventoryLocation(name="Source Bin", type="Bin", active=True)
        destination = InventoryLocation(name="Destination Bin", type="Bin", active=True)
        db.session.add_all([source, destination])
        db.session.flush()
        record = InventoryRecord(product_id=product.id, location_id=source.id, quantity_on_hand=8, quantity_reserved=0)
        db.session.add(record)
        db.session.commit()

        reserve_inventory(record_id=record.id, quantity=3)
        release_inventory(record_id=record.id, quantity=1)
        source_record, destination_record = transfer_inventory(record_id=record.id, to_location_id=destination.id, quantity=4)
        db.session.commit()

        assert source_record.quantity_on_hand == 4
        assert destination_record.quantity_on_hand == 4
        assert InventoryMovement.query.count() == 4


def test_cost_engine_and_initial_snapshot_use_product_model_fields(app):
    with app.app_context():
        product = _product()
        spool = _add_spool()
        product.analysis_status = "complete"
        product.parsed_filament_grams = Decimal("42.00")
        product.parsed_print_minutes = Decimal("84.00")
        product.parsed_volume_mm3 = Decimal("1000.00")
        product.model_file_path = "/tmp/foundation.stl"
        db.session.flush()

        breakdown = calculate_product_cost(product=product)
        assert breakdown.total_cost > Decimal("0")
        assert breakdown.evidence_source == "generated_slice.product"

        _apply_initial_cost_snapshot(product)
        db.session.commit()

        snapshot = CostSnapshot.query.filter_by(product_id=product.id, stale=False).first()
        assert snapshot is not None
        assert snapshot.filament_spool_id == spool.id


def test_market_prep_generation(app):
    with app.app_context():
        product = _product()
        location = InventoryLocation(name="Prep Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        db.session.add(InventoryRecord(product_id=product.id, location_id=location.id, quantity_on_hand=0))
        market = Market(name="Foundation Market", event_date=date(2026, 7, 1), status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.commit()

        tasks = generate_market_prep_tasks(market.id)
        readiness = market_readiness_score(market.id)

        assert len(tasks) >= 1
        assert readiness["total"] == len(tasks)
        assert readiness["score"] == Decimal("0.00")


def test_inventory_deduction_blocks_negative(app):
    with app.app_context():
        product = _product()
        location = InventoryLocation(name="No Negative Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
        db.session.add(InventoryRecord(product_id=product.id, location_id=location.id, quantity_on_hand=1))
        db.session.commit()

        with pytest.raises(ValueError, match="Insufficient inventory"):
            deduct_finished_goods(
                product_id=product.id,
                quantity=2,
                location_id=location.id,
                reference_type="test",
                reference_id="abc",
            )
