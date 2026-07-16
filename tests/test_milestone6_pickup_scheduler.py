from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    Customer,
    InventoryLocation,
    InventoryRecord,
    Order,
    OrderFulfillmentMethod,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    PickupLocation,
    PickupLocationType,
    PickupSlot,
    PickupSlotStatus,
    PickupStatus,
    PrepTask,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.api_tokens import create_api_token
from app.services.pickup import (
    PickupError,
    assign_order_pickup,
    generate_pickup_batch_prep_tasks,
    pickup_board_groups,
    transition_pickup,
    validate_pickup_slot,
)


def _slot(*, capacity: int = 3, starts_delta: timedelta = timedelta(days=1)) -> PickupSlot:
    location = PickupLocation(
        name="Market Table Pickup",
        location_type=PickupLocationType.MARKET,
        instructions="Pick up at the Dude Fish booth.",
    )
    slot = PickupSlot(
        location=location,
        starts_at=datetime.now(timezone.utc) + starts_delta,
        ends_at=datetime.now(timezone.utc) + starts_delta + timedelta(hours=2),
        capacity=capacity,
        status=PickupSlotStatus.OPEN,
        public_label="Saturday market pickup",
    )
    db.session.add(slot)
    db.session.commit()
    return slot


def _order(email: str = "pickup@example.com") -> Order:
    customer = Customer(first_name="Pickup", last_name="Buyer", email=email, is_active=True)
    order = Order(
        customer=customer,
        customer_name="Pickup Buyer",
        customer_email=email,
        status=OrderStatus.PENDING,
        source=OrderSource.ONLINE,
        payment_status=OrderPaymentStatus.UNPAID,
        fulfillment_method=OrderFulfillmentMethod.PICKUP,
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )
    db.session.add(order)
    db.session.commit()
    return order


def _public_product() -> Product:
    category = Category(name="Pickup Products", slug="pickup-products", is_public=True)
    product = Product(
        name="Pickup Turtle",
        slug="pickup-turtle",
        sku_base="PICKUP-TURTLE",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_public=True,
        is_pos_visible=True,
        base_price=Decimal("12.00"),
    )
    location = InventoryLocation(name="Pickup Shelf", type="shelf")
    db.session.add_all([category, product, location])
    db.session.flush()
    db.session.add(InventoryRecord(product=product, location=location, quantity_on_hand=5))
    db.session.commit()
    return product


def test_pickup_slot_validation_rejects_past_or_full_slots(app):
    with app.app_context():
        past = _slot(starts_delta=timedelta(days=-1))
        try:
            validate_pickup_slot(past)
        except PickupError as exc:
            assert "already passed" in str(exc)
        else:
            raise AssertionError("past slot should not validate")

        full = _slot(capacity=1)
        assign_order_pickup(_order("one@example.com"), full)
        try:
            validate_pickup_slot(full)
        except PickupError as exc:
            assert "full" in str(exc)
        else:
            raise AssertionError("full slot should not validate")


def test_public_checkout_assigns_pickup_slot(client, app):
    with app.app_context():
        product = _public_product()
        slot = _slot()
        slug = product.slug
        product_id = product.id
        slot_id = slot.id

    client.post(f"/shop/{slug}", data={"product_id": str(product_id), "quantity": "1"})
    response = client.post(
        "/checkout",
        data={
            "first_name": "Pickup",
            "last_name": "Customer",
            "email": "pickup-customer@example.com",
            "phone": "931-555-0101",
            "fulfillment_method": "pickup",
            "pickup_slot_id": str(slot_id),
            "payment_option": "venmo",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        order = Order.query.filter_by(customer_email="pickup-customer@example.com").one()
        assert order.pickup_slot_id == slot_id
        assert order.pickup_status == PickupStatus.SCHEDULED.value


def test_pickup_board_transition_and_prep_task_generation(app):
    with app.app_context():
        slot = _slot()
        order = assign_order_pickup(_order(), slot)

        transition_pickup(order, PickupStatus.READY)
        assert order.pickup_status == PickupStatus.READY.value
        assert order.pickup_ready_at is not None

        groups = pickup_board_groups()
        assert len(groups) == 1
        assert groups[0].total_items == 1

        count = generate_pickup_batch_prep_tasks(groups)
        assert count == 1
        task = PrepTask.query.filter_by(source="pickup_scheduler").one()
        assert "Prep pickup batch" in task.title


def test_pickup_api_resources_and_transition(client, app):
    with app.app_context():
        user = User(email="pickup-api@example.com", first_name="Pickup", last_name="API", role=UserRole.ADMIN)
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _token, raw = create_api_token(user, "Pickup API", scopes=["orders"])
    headers = {"Authorization": f"Bearer {raw}"}
    location_resp = client.post(
        "/api/v1/pickup-locations",
        json={
            "name": "Porch Pickup",
            "location_type": "porch",
            "address": "Clarksville",
            "instructions": "Text before arrival.",
            "active": True,
        },
        headers=headers,
    )
    assert location_resp.status_code == 201
    location_id = location_resp.get_json()["id"]

    starts = datetime.now(timezone.utc) + timedelta(days=2)
    slot_resp = client.post(
        "/api/v1/pickup-slots",
        json={
            "location_id": location_id,
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=1)).isoformat(),
            "capacity": 4,
            "status": "open",
            "public_label": "Porch window",
        },
        headers=headers,
    )
    assert slot_resp.status_code == 201

    with app.app_context():
        order = assign_order_pickup(_order("api-pickup@example.com"), db.session.get(PickupSlot, slot_resp.get_json()["id"]))
        order_id = order.id

    transition_resp = client.post(
        "/api/v1/pickup-board/transition",
        json={"entity_type": "order", "entity_id": order_id, "status": "handed_off"},
        headers=headers,
    )
    assert transition_resp.status_code == 200
    assert transition_resp.get_json()["status"] == "handed_off"
