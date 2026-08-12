from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import (
    Category,
    Collection,
    InventoryLocation,
    InventoryRecord,
    Order,
    OrderPaymentStatus,
    OrderSource,
    PickupLocation,
    PickupLocationType,
    PickupSlot,
    PickupSlotStatus,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.square_checkout import SquarePaymentLink


def _create_public_product_with_inventory():
    category = Category(
        name="Flexis",
        slug="flexis",
        description="Flexi animals",
        sort_order=10,
        is_public=True,
        is_pos_visible=True,
    )
    collection = Collection(
        name="Market Favorites",
        slug="market-favorites",
        description="Best sellers",
        is_public=True,
        sort_order=10,
    )
    product = Product(
        name="Flexi Turtle",
        slug="flexi-turtle",
        sku_base="FLEXI-TURTLE",
        short_description="A bendy turtle friend.",
        description="A bendy turtle friend.",
        category=category,
        collection=collection,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_public=True,
        is_pos_visible=True,
        is_featured=True,
        base_price=Decimal("18.00"),
        estimated_material_cost=Decimal("2.00"),
        estimated_labor_minutes=5,
        estimated_print_minutes=90,
        estimated_profit=Decimal("16.00"),
    )
    location = InventoryLocation(name="Website Shelf", type="shelf", active=True)
    db.session.add_all([category, collection, product, location])
    db.session.flush()
    pickup_location = PickupLocation(
        name="Clarksville Porch Pickup",
        location_type=PickupLocationType.PORCH,
        instructions="Wait for ready text before arriving.",
    )
    db.session.add(pickup_location)
    db.session.flush()
    pickup_slot = PickupSlot(
        location=pickup_location,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        ends_at=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=6,
        status=PickupSlotStatus.OPEN,
        public_label="Tomorrow pickup",
    )
    db.session.add(pickup_slot)
    db.session.add(
        InventoryRecord(
            product_id=product.id,
            location_id=location.id,
            quantity_on_hand=6,
            quantity_reserved=0,
            reorder_threshold=1,
            reorder_target=8,
        )
    )
    db.session.commit()
    return product


def test_public_cart_page_and_checkout_page_load(client, app):
    with app.app_context():
        product = _create_public_product_with_inventory()
        slug = product.slug
        product_id = product.id

    add_response = client.post(
        f"/shop/{slug}",
        data={"product_id": str(product_id), "quantity": "2"},
        follow_redirects=True,
    )

    assert add_response.status_code == 200
    assert b"Flexi Turtle added to your cart" in add_response.data
    assert b"Your order" in add_response.data

    checkout_response = client.get("/checkout")
    assert checkout_response.status_code == 200
    assert b"Finish your order" in checkout_response.data


def test_public_home_page_avoids_unsupported_metrics(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Ideas shared" not in response.data
    assert b"Satisfaction %" not in response.data
    assert b"Cities reached" not in response.data


def test_public_policy_pages_use_real_copy(client):
    expectations = {
        "/privacy": [b"Information We Collect", b"How We Use Information"],
        "/terms": [b"Orders and Payment", b"Custom and Personalized Work"],
        "/shipping-policy": [b"Order Processing", b"Shipping and Delivery"],
        "/accessibility": [b"Accessibility Commitment", b"Contact Us for Accessibility Help"],
    }

    placeholder_phrases = [
        b"This placeholder page exists",
        b"This is a placeholder",
        b"will be drafted before the site launches publicly",
    ]

    for path, required_snippets in expectations.items():
        response = client.get(path)
        assert response.status_code == 200
        for snippet in required_snippets:
            assert snippet in response.data
        for phrase in placeholder_phrases:
            assert phrase not in response.data


def test_public_checkout_venmo_creates_order_and_reserves_inventory(client, app):
    with app.app_context():
        product = _create_public_product_with_inventory()
        slug = product.slug
        product_id = product.id

    client.post(f"/shop/{slug}", data={"product_id": str(product_id), "quantity": "2"})

    response = client.post(
        "/checkout",
        data={
            "first_name": "Jamie",
            "last_name": "Buyer",
            "email": "jamie@example.com",
            "phone": "931-555-1111",
            "fulfillment_method": "pickup",
            "pickup_slot_id": "1",
            "payment_option": "venmo",
            "notes": "Please save one teal one if possible.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/checkout/confirmation/" in response.headers["Location"]

    with app.app_context():
        order = Order.query.filter_by(customer_email="jamie@example.com").one()
        inventory = InventoryRecord.query.filter_by(product_id=product_id).one()

        assert order.source == OrderSource.ONLINE
        assert order.payment_provider == "venmo"
        assert order.payment_status == OrderPaymentStatus.UNPAID
        assert order.total == Decimal("18.00") * 2
        assert len(order.items) == 1
        assert inventory.quantity_reserved == 0


def test_public_checkout_square_redirects_when_configured(client, app, monkeypatch):
    with app.app_context():
        product = _create_public_product_with_inventory()
        slug = product.slug
        product_id = product.id

    client.application.config.update(
        {
            "SQUARE_ACCESS_TOKEN": "test-token",
            "SQUARE_LOCATION_ID": "test-location",
            "SQUARE_API_BASE_URL": "https://example.com",
        }
    )

    monkeypatch.setattr(
        "app.blueprints.public.routes.create_payment_link",
        lambda order, config: SquarePaymentLink(
            payment_link_id="plink-123",
            url="https://square.example.test/checkout",
            long_url="https://square.example.test/checkout",
        ),
    )

    client.post(f"/shop/{slug}", data={"product_id": str(product_id), "quantity": "1"})

    response = client.post(
        "/checkout",
        data={
            "first_name": "Square",
            "last_name": "Buyer",
            "email": "square@example.com",
            "phone": "931-555-2222",
            "fulfillment_method": "pickup",
            "pickup_slot_id": "1",
            "payment_option": "square",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "https://square.example.test/checkout"

    with app.app_context():
        order = Order.query.filter_by(customer_email="square@example.com").one()
        assert order.external_checkout_id == "plink-123"
        assert order.external_checkout_url == "https://square.example.test/checkout"
