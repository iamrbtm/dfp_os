from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import Category, Product, ProductStatus, ProductType
from app.services.admin_mutations import create_resource


def test_product_model_can_be_created(app):
    with app.app_context():
        category = Category(
            name="Fidgets",
            slug="fidgets",
            description="Fidgets",
            sort_order=20,
            is_public=True,
            is_pos_visible=True,
        )
        product = Product(
            name="Fidget Slider",
            slug="fidget-slider",
            sku_base="FGT-SLIDER",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_public=True,
            is_pos_visible=True,
            is_featured=False,
            base_price=8,
            estimated_material_cost=1,
            estimated_labor_minutes=5,
            estimated_print_minutes=45,
            estimated_profit=7,
        )
        db.session.add_all([category, product])
        db.session.commit()

        stored = Product.query.filter_by(slug="fidget-slider").first()
        assert stored is not None
        assert stored.category.slug == "fidgets"


def test_product_admin_list_loads(client, login_admin, catalog_product):
    response = client.get("/products/products/")

    assert response.status_code == 200
    assert b"Products" in response.data
    assert b"Rainbow Dragon" in response.data


def test_public_shop_page_loads_public_product(client, catalog_product):
    response = client.get("/shop")

    assert response.status_code == 200
    assert b"Rainbow Dragon" in response.data


def test_product_api_requires_token(client, catalog_product):
    response = client.get("/api/v1/products")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_api_token"


def test_product_api_returns_data_with_token(client, catalog_product, api_token):
    response = client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {api_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["slug"] == "rainbow-dragon"


def test_product_admin_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        category = Category(
            name="Audit Catalog",
            slug="audit-catalog",
            is_public=True,
            is_pos_visible=True,
        )
        db.session.add(category)
        db.session.flush()
        product = Product(
            name="Audit Product",
            slug="audit-product",
            category_id=category.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("9.00"),
        )
        create_resource(product, actor_id=123)

    assert any(call["action"] == "product.created" for call in calls)
