from __future__ import annotations

from app.extensions import db
from decimal import Decimal

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
    ProductVariant,
    User,
    UserRole,
)
from app.services.business import ensure_default_business
from app.services.pos import create_sale, open_session


def test_public_gallery_page_loads(client, catalog_product):
    response = client.get("/gallery")
    assert response.status_code == 200
    assert b"Gallery" in response.data


def test_public_accessibility_page_loads(client):
    response = client.get("/accessibility")
    assert response.status_code == 200
    assert b"Accessibility" in response.data


def test_public_shipping_policy_page_loads(client):
    response = client.get("/shipping-policy")
    assert response.status_code == 200
    assert b"Shipping Policy" in response.data


def test_business_settings_page_loads_for_admin(client, login_admin):
    response = client.get("/settings/business")
    assert response.status_code == 200
    assert b"Business Settings" in response.data


def test_business_settings_update(client, login_admin):
    with client.application.app_context():
        business = ensure_default_business()
        business_id = business.id
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
        business = db.session.get(Business, business_id)
        assert business.legal_name == "Dude Fish Printing LLC"


def test_feature_flag_crud_pages(client, login_admin):
    response = client.get("/settings/feature-flags")
    assert response.status_code == 200
    create_response = client.post(
        "/settings/feature-flags/new",
        data={"key": "module.test.enabled", "enabled": "y", "description": "Test flag", "business_id": "0"},
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    with client.application.app_context():
        assert FeatureFlag.query.filter_by(key="module.test.enabled").first() is not None


def test_module_status_update_creates_override(client, login_admin):
    response = client.post("/settings/modules/update", data={"module.products.enabled": "on"}, follow_redirects=False)
    assert response.status_code == 302
    with client.application.app_context():
        assert FeatureFlag.query.filter_by(key="module.products.enabled").first() is not None


def test_module_status_update_keeps_critical_modules_enabled(client, login_admin):
    response = client.post("/settings/modules/update", data={}, follow_redirects=False)
    assert response.status_code == 302
    with client.application.app_context():
        auth_flag = FeatureFlag.query.filter_by(key="module.auth.enabled").first()
        settings_flag = FeatureFlag.query.filter_by(key="module.settings.enabled").first()
        assert auth_flag is not None
        assert settings_flag is not None
        assert auth_flag.enabled is True
        assert settings_flag.enabled is True


def test_prep_task_admin_pages(client, login_admin):
    response = client.get("/prep-tasks/tasks/")
    assert response.status_code == 200
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
        assert PrepTaskTemplate.query.filter_by(title="Pack batteries").first() is not None


def test_cost_engine_page_loads(client, login_admin):
    response = client.get("/cost-engine/")
    assert response.status_code == 200
    assert b"Cost Engine" in response.data


def test_audit_logs_page_loads_without_config(client, login_admin):
    response = client.get("/audit-logs/")
    assert response.status_code == 200
    assert b"Audit Logs" in response.data


def test_businesses_api_returns_data_with_token(api_token, client):
    with client.application.app_context():
        ensure_default_business()
    response = client.get("/api/v1/businesses", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    assert isinstance(response.get_json()["data"], list)


def test_feature_flags_api_returns_data_with_token(api_token, client):
    response = client.get("/api/v1/feature-flags", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200


def test_prep_task_templates_api_returns_data_with_token(api_token, client):
    response = client.get("/api/v1/prep-task-templates", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200


def test_prep_tasks_api_returns_data_with_token(api_token, client):
    with client.application.app_context():
        db.session.add(
            PrepTask(
                title="Test task",
                category=PrepTaskCategory.GENERAL,
                status=PrepTaskStatus.OPEN,
                source="manual",
            )
        )
        db.session.commit()
    response = client.get("/api/v1/prep-tasks", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200


def test_inventory_operation_apis_work(api_token, client, app):
    with app.app_context():
        category = Category(name="Ops", slug="ops", is_public=False, is_pos_visible=False)
        product = Product(
            name="Ops Product",
            slug="ops-product",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("5.00"),
        )
        variant = ProductVariant(product=product, sku="OPS-1", name="Default", price=Decimal("5.00"), active=True)
        source = InventoryLocation(name="API Source", type="Bin", active=True)
        destination = InventoryLocation(name="API Destination", type="Bin", active=True)
        db.session.add_all([category, product, variant, source, destination])
        db.session.flush()
        record = InventoryRecord(
            product_id=product.id,
            variant_id=variant.id,
            location_id=source.id,
            quantity_on_hand=6,
            quantity_reserved=0,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id
        destination_id = destination.id

    reserve = client.post(
        f"/api/v1/inventory-records/{record_id}/reserve",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"quantity": 2},
    )
    assert reserve.status_code == 200
    assert reserve.get_json()["data"]["quantity_reserved"] == 2

    release = client.post(
        f"/api/v1/inventory-records/{record_id}/release",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"quantity": 1},
    )
    assert release.status_code == 200
    assert release.get_json()["data"]["quantity_reserved"] == 1

    transfer = client.post(
        f"/api/v1/inventory-records/{record_id}/transfer",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"quantity": 3, "to_location_id": destination_id},
    )
    assert transfer.status_code == 200
    assert transfer.get_json()["data"]["destination_quantity_on_hand"] == 3


def test_pos_refund_api_works(api_token, client, app):
    with app.app_context():
        user = User(
            email="refund-api@example.com",
            first_name="Refund",
            last_name="API",
            role=UserRole.ADMIN,
            is_active=True,
        )
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
        variant = ProductVariant(product=product, sku="REF-1", name="Default", price=Decimal("12.00"), active=True)
        location = InventoryLocation(name="Refund Bin", type="Bin", active=True)
        db.session.add_all([user, category, product, variant, location])
        db.session.flush()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                variant_id=variant.id,
                location_id=location.id,
                quantity_on_hand=5,
                quantity_reserved=0,
            )
        )
        db.session.commit()

        session = open_session(user_id=user.id, opening_cash=Decimal("20.00"), inventory_location_id=location.id)
        sale, _order = create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("12.00"),
            items=[
                {
                    "product_id": product.id,
                    "variant_id": variant.id,
                    "quantity": 1,
                    "unit_price": "12.00",
                    "description": "Refund Product",
                    "item_type": "product",
                }
            ],
        )
        sale_id = sale.id

    response = client.post(
        f"/api/v1/pos-sales/{sale_id}/refund",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"restock_inventory": True, "notes": "API refund"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "refunded"


def test_catalog_scoped_token_cannot_use_inventory_operation_api(api_token, client, app):
    with app.app_context():
        category = Category(name="Scoped Ops", slug="scoped-ops", is_public=False, is_pos_visible=False)
        product = Product(
            name="Scoped Product",
            slug="scoped-product",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("5.00"),
        )
        variant = ProductVariant(product=product, sku="SCOPE-1", name="Default", price=Decimal("5.00"), active=True)
        source = InventoryLocation(name="Scoped Source", type="Bin", active=True)
        destination = InventoryLocation(name="Scoped Destination", type="Bin", active=True)
        db.session.add_all([category, product, variant, source, destination])
        db.session.flush()
        record = InventoryRecord(
            product_id=product.id,
            variant_id=variant.id,
            location_id=source.id,
            quantity_on_hand=2,
            quantity_reserved=0,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id
        destination_id = destination.id

    response = client.post(
        f"/api/v1/inventory-records/{record_id}/transfer",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"quantity": 1, "to_location_id": destination_id},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "insufficient_scope"


def test_catalog_scoped_token_cannot_use_analytics_api(api_token, client):
    response = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "insufficient_scope"
