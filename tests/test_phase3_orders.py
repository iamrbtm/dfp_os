from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    CustomRequest,
    CustomRequestStatus,
    Customer,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Payment,
    PaymentMethod,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.custom_requests import create_custom_request
from app.services.customers import create_customer
from app.services.order_admin import create_order_resource


def test_customer_model_and_service(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        customer = Customer(first_name="Jane", last_name="Doe", email="jane@example.com", is_active=True)
        create_customer(customer, actor_id=123)
        stored = Customer.query.filter_by(email="jane@example.com").first()
        assert stored is not None
        assert stored.full_name == "Jane Doe"

    assert any(call["action"] == "customer.created" for call in calls)


def test_public_custom_order_form_submission(client):
    response = client.post(
        "/custom-orders",
        data={"name": "Public User", "email": "public@example.com", "description": "Please make a custom fidget toy."},
    )
    assert response.status_code == 200
    assert b"Request received" in response.data


def test_custom_request_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        request = CustomRequest(
            name="Audit Request",
            email="audit-request@example.com",
            description="Audit this request",
            status=CustomRequestStatus.NEW,
            source="website",
        )
        create_custom_request(request, actor_type="anonymous")

    assert any(call["action"] == "custom_request.created" for call in calls)


def test_order_with_items_payment_and_print_job(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        customer = Customer(first_name="Order", last_name="Customer", email="order@example.com", is_active=True)
        category = Category(name="Orders", slug="orders")
        product = Product(
            name="Order Product",
            slug="order-product",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("20.00"),
        )
        order = Order(
            customer=customer,
            status=OrderStatus.CONFIRMED,
            source=OrderSource.POS,
            subtotal=Decimal("20.00"),
            total=Decimal("20.00"),
            paid_amount=Decimal("20.00"),
        )
        db.session.add_all([customer, category, product, order])
        db.session.flush()
        item = OrderItem(
            order=order,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("20.00"),
            line_total=Decimal("20.00"),
        )
        payment = Payment(order=order, amount=Decimal("20.00"), method=PaymentMethod.CASH)
        job = PrintJob(order_item=item, product=product, status=PrintJobStatus.QUEUED, estimated_minutes=120, label="Test print job")
        db.session.add_all([item, payment, job])
        db.session.commit()

        created = Order(
            status=OrderStatus.PENDING,
            source=OrderSource.MANUAL,
            subtotal=Decimal("12.00"),
            total=Decimal("12.00"),
            paid_amount=Decimal("0.00"),
        )
        create_order_resource(created, actor_id=123)

        assert order.balance_due == Decimal("0.00")
        assert len(order.items) == 1
        assert len(order.payments) == 1
        assert PrintJob.query.filter_by(label="Test print job").one().status == PrintJobStatus.QUEUED

    assert any(call["action"] == "order.created" for call in calls)
