from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Business,
    Category,
    FeatureFlag,
    InventoryLocation,
    InventoryRecord,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    PrepTaskTemplate,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.admin_mutations import create_resource
from app.services.api_tokens import create_api_token
from app.services.pos import create_sale, open_session


def test_settings_and_prep_task_pages(client, login_admin):
    assert client.get("/settings/business").status_code == 200
    assert client.get("/prep-tasks/tasks/").status_code == 200
    assert client.get("/cost-engine/").status_code == 200


def test_business_settings_update(client, login_admin):
    response = client.post(
        "/settings/business",
        data={
            "name": "Dude Fish Printing",
            "slug": "dude-fish-printing",
            "legal_name": "Dude Fish Printing LLC",
            "public_name": "Dude Fish Printing",
            "contact_email": "hello@example.com",
            "phone": "931-555-0000",
            "website_url": "",
            "address_line1": "123 Main St",
            "address_line2": "",
            "city": "Clarksville",
            "state": "TN",
            "postal_code": "37040",
            "timezone": "America/Chicago",
            "currency": "USD",
            "is_active": "y",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.application.app_context():
        business = Business.query.filter_by(slug="dude-fish-printing").first()
        assert business is not None
        assert business.legal_name == "Dude Fish Printing LLC"


def test_feature_flag_and_prep_task_template_creation(client, login_admin):
    feature_response = client.post(
        "/settings/feature-flags/new",
        data={"key": "module.test.enabled", "enabled": "y", "description": "Test flag", "business_id": "0"},
        follow_redirects=False,
    )
    assert feature_response.status_code == 302

    template_response = client.post(
        "/prep-tasks/templates/new",
        data={
            "title": "Pack batteries",
            "category": "supply",
            "description": "Bring backups",
            "default_due_days_before": "2",
            "default_enabled": "y",
        },
        follow_redirects=False,
    )
    assert template_response.status_code == 302

    with client.application.app_context():
        assert FeatureFlag.query.filter_by(key="module.test.enabled").first() is not None
        assert PrepTaskTemplate.query.filter_by(title="Pack batteries").first() is not None


def test_inventory_operation_apis_work(client, app):
    with app.app_context():
        user = User(email="inventory-api@example.com", first_name="Inventory", last_name="API", role=UserRole.ADMIN, is_active=True)
        user.set_password("secret")
        category = Category(name="Ops", slug="ops", is_public=False, is_pos_visible=False)
        product = Product(
            name="Ops Product",
            slug="ops-product",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("5.00"),
        )
        source = InventoryLocation(name="API Source", type="Bin", active=True)
        destination = InventoryLocation(name="API Destination", type="Bin", active=True)
        db.session.add_all([user, category, product, source, destination])
        db.session.flush()
        _token, raw_token = create_api_token(user, "Inventory Ops", scopes=["inventory"])
        record = InventoryRecord(product_id=product.id, location_id=source.id, quantity_on_hand=6, quantity_reserved=0)
        db.session.add(record)
        db.session.commit()
        record_id = record.id
        destination_id = destination.id

    reserve = client.post(
        f"/api/v1/inventory-records/{record_id}/reserve",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"quantity": 2},
    )
    assert reserve.status_code == 200

    release = client.post(
        f"/api/v1/inventory-records/{record_id}/release",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"quantity": 1},
    )
    assert release.status_code == 200

    transfer = client.post(
        f"/api/v1/inventory-records/{record_id}/transfer",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"quantity": 3, "to_location_id": destination_id},
    )
    assert transfer.status_code == 200
    assert transfer.get_json()["data"]["destination_quantity_on_hand"] == 3


def test_pos_refund_api_works(client, app):
    with app.app_context():
        user = User(email="refund-api@example.com", first_name="Refund", last_name="API", role=UserRole.ADMIN, is_active=True)
        user.set_password("secret")
        category = Category(name="Refund Ops", slug="refund-ops", is_public=False, is_pos_visible=True)
        product = Product(
            name="Refund Product",
            slug="refund-product",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_pos_visible=True,
            base_price=Decimal("12.00"),
        )
        location = InventoryLocation(name="Refund Bin", type="Bin", active=True)
        db.session.add_all([user, category, product, location])
        db.session.flush()
        _token, raw_token = create_api_token(user, "POS Refund", scopes=["pos"])
        db.session.add(InventoryRecord(product_id=product.id, location_id=location.id, quantity_on_hand=5, quantity_reserved=0))
        db.session.commit()

        session = open_session(user_id=user.id, opening_cash=Decimal("20.00"), inventory_location_id=location.id)
        sale, _order = create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("12.00"),
            items=[{"product_id": product.id, "quantity": 1, "unit_price": "12.00", "description": "Refund Product", "item_type": "product"}],
        )
        sale_id = sale.id

    response = client.post(
        f"/api/v1/pos-sales/{sale_id}/refund",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"restock_inventory": True, "notes": "API refund"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "refunded"


def test_admin_mutation_audits_for_inventory_and_prep_templates(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        create_resource(InventoryLocation(name="Audit Shelf", type="Shelf", active=True), actor_id=123)
        create_resource(
            PrepTaskTemplate(
                title="Audit Prep Template",
                category=PrepTaskCategory.GENERAL,
                default_due_days_before=3,
                default_enabled=True,
            ),
            actor_id=123,
        )
        db.session.add(PrepTask(title="Task", category=PrepTaskCategory.GENERAL, status=PrepTaskStatus.OPEN, source="manual"))
        db.session.commit()

    actions = {call["action"] for call in calls}
    assert "inventory_location.created" in actions
    assert "prep_task_template.created" in actions
