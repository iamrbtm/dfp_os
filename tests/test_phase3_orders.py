from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    AMSUnit,
    AMSUnitType,
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
    ProductVariant,
    Printer,
    PrinterStatus,
)
from app.services.admin_mutations import create_resource
from app.services.custom_requests import create_custom_request
from app.services.customers import create_customer
from app.services.order_admin import create_order_resource
from app.services.print_jobs import create_print_job


def test_customer_model_can_be_created(app):
    with app.app_context():
        customer = Customer(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="931-555-9999",
            is_active=True,
        )
        db.session.add(customer)
        db.session.commit()

        stored = Customer.query.filter_by(email="jane@example.com").first()
        assert stored is not None
        assert stored.full_name == "Jane Doe"


def test_customer_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        customer = Customer(
            first_name="Audit",
            last_name="Customer",
            email="audit-customer@example.com",
            is_active=True,
        )
        create_customer(customer, actor_id=123)

    assert any(call["action"] == "customer.created" for call in calls)


def test_custom_request_model_can_be_created(app):
    with app.app_context():
        req = CustomRequest(
            name="Test User",
            email="test@example.com",
            description="I want a custom dragon.",
            status=CustomRequestStatus.NEW,
            source="website",
        )
        db.session.add(req)
        db.session.commit()

        stored = CustomRequest.query.filter_by(email="test@example.com").first()
        assert stored is not None
        assert stored.status == CustomRequestStatus.NEW


def test_customer_admin_list_loads(client, login_admin):
    with client.application.app_context():
        customer = Customer(
            first_name="Admin",
            last_name="View",
            email="adminview@example.com",
            is_active=True,
        )
        db.session.add(customer)
        db.session.commit()

    response = client.get("/customers/customers/")
    assert response.status_code == 200
    assert b"Customers" in response.data
    assert b"adminview@example.com" in response.data


def test_public_custom_order_form_loads(client):
    response = client.get("/custom-orders")
    assert response.status_code == 200
    assert b"Custom 3D Printing Requests" in response.data


def test_public_custom_order_form_submission(client):
    response = client.post(
        "/custom-orders",
        data={
            "name": "Public User",
            "email": "public@example.com",
            "description": "Please make a custom fidget toy.",
        },
    )
    assert response.status_code == 200
    assert b"Request received" in response.data

    with client.application.app_context():
        req = CustomRequest.query.filter_by(email="public@example.com").first()
        assert req is not None
        assert req.source == "website"


def test_custom_request_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        req = CustomRequest(
            name="Audit Request",
            email="audit-request@example.com",
            description="Audit this request",
            status=CustomRequestStatus.NEW,
            source="website",
        )
        create_custom_request(req, actor_type="anonymous")

    assert any(call["action"] == "custom_request.created" for call in calls)


def test_order_model_can_be_created(app):
    with app.app_context():
        customer = Customer(
            first_name="Order",
            last_name="Test",
            email="ordertest@example.com",
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()

        order = Order(
            customer=customer,
            status=OrderStatus.PENDING,
            source=OrderSource.MANUAL,
            subtotal=Decimal("50.00"),
            total=Decimal("50.00"),
            paid_amount=Decimal("0.00"),
        )
        db.session.add(order)
        db.session.commit()

        stored = Order.query.filter_by(customer=customer).first()
        assert stored is not None
        assert stored.order_number.startswith("DFP-")


def test_order_admin_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        order = Order(
            status=OrderStatus.PENDING,
            source=OrderSource.MANUAL,
            subtotal=Decimal("12.00"),
            total=Decimal("12.00"),
            paid_amount=Decimal("0.00"),
        )
        create_order_resource(order, actor_id=123)

    assert any(call["action"] == "order.created" for call in calls)


def test_order_with_items_and_payment(app):
    with app.app_context():
        customer = Customer(
            first_name="Full",
            last_name="Order",
            email="fullorder@example.com",
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()

        order = Order(
            customer=customer,
            status=OrderStatus.CONFIRMED,
            source=OrderSource.POS,
            subtotal=Decimal("20.00"),
            total=Decimal("20.00"),
            paid_amount=Decimal("20.00"),
        )
        db.session.add(order)
        db.session.flush()

        item = OrderItem(
            order=order,
            is_custom_item=True,
            custom_description="Custom keychain",
            quantity=1,
            unit_price=Decimal("20.00"),
            line_total=Decimal("20.00"),
        )
        db.session.add(item)

        payment = Payment(
            order=order,
            amount=Decimal("20.00"),
            method=PaymentMethod.CASH,
            notes="Cash at market",
        )
        db.session.add(payment)
        db.session.commit()

        assert len(order.items) == 1
        assert order.items[0].custom_description == "Custom keychain"
        assert len(order.payments) == 1
        assert order.payments[0].method == PaymentMethod.CASH
        assert order.balance_due == Decimal("0.00")


def test_print_job_model_can_be_created(app):
    with app.app_context():
        job = PrintJob(
            status=PrintJobStatus.QUEUED,
            priority=2,
            estimated_minutes=120,
            label="Test print job",
        )
        db.session.add(job)
        db.session.commit()

        stored = PrintJob.query.filter_by(label="Test print job").first()
        assert stored is not None
        assert stored.status == PrintJobStatus.QUEUED


def test_printer_admin_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        printer = Printer(name="Audit Printer", model="Bambu A1", status=PrinterStatus.ACTIVE)
        create_resource(printer, actor_id=123)

    assert any(call["action"] == "printer.created" for call in calls)


def test_ams_admin_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        ams = AMSUnit(name="Audit AMS", type=AMSUnitType.AMS_LITE)
        create_resource(ams, actor_id=123)

    assert any(call["action"] == "ams_unit.created" for call in calls)


def test_print_job_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        job = PrintJob(status=PrintJobStatus.QUEUED, label="Audit print job")
        create_print_job(job, actor_id=123)

    assert any(call["action"] == "print_job.created" for call in calls)


def test_pos_sale_creates_order_and_payment(client, login_admin):
    with client.application.app_context():
        category = _ensure_category()
        product = _ensure_product(category)
        _ensure_variant(product)

    response = client.post(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {_get_token(client)}"},
        json={
            "status": "confirmed",
            "source": "pos",
            "total": "15.00",
            "paid_amount": "15.00",
        },
    )

    assert response.status_code == 201


def test_custom_request_api_returns_data_with_token(client, api_token):
    response = client.get(
        "/api/v1/custom-requests",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 200


def test_order_api_requires_token(client, catalog_product):
    response = client.get("/api/v1/orders")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_api_token"


def test_orders_customers_print_jobs_list_api_with_token(client, api_token):
    for endpoint in ["orders", "customers", "custom-requests", "print-jobs"]:
        response = client.get(
            f"/api/v1/{endpoint}",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert response.status_code == 200, f"API endpoint /api/v1/{endpoint} failed"


def test_custom_request_conversion_workflow(app):
    with app.app_context():
        req = CustomRequest(
            name="Convert Test",
            email="convert@example.com",
            description="Test conversion",
            status=CustomRequestStatus.NEW,
            source="website",
        )
        db.session.add(req)
        db.session.flush()

        customer = Customer(
            first_name="Convert",
            last_name="Test",
            email="convert@example.com",
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()

        order = Order(
            customer=customer,
            source=OrderSource.CUSTOM,
            status=OrderStatus.PENDING,
            subtotal=Decimal("30.00"),
            total=Decimal("30.00"),
            paid_amount=Decimal("10.00"),
        )
        db.session.add(order)
        db.session.flush()

        item = OrderItem(
            order=order,
            is_custom_item=True,
            custom_description=req.description,
            quantity=1,
            unit_price=Decimal("30.00"),
            line_total=Decimal("30.00"),
        )
        db.session.add(item)

        payment = Payment(
            order=order,
            amount=Decimal("10.00"),
            method=PaymentMethod.CASH,
            notes="Deposit for custom order",
        )
        db.session.add(payment)

        req.converted_to_order_id = order.id
        req.customer_id = customer.id
        req.status = CustomRequestStatus.DEPOSIT_COLLECTED
        db.session.commit()

        assert req.converted_to_order_id == order.id
        assert req.status == CustomRequestStatus.DEPOSIT_COLLECTED
        assert order.balance_due == Decimal("20.00")


def _ensure_category():
    cat = Category.query.filter_by(slug="test-pos-cat").first()
    if cat:
        return cat
    cat = Category(name="Test POS Cat", slug="test-pos-cat", is_public=True, is_pos_visible=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _ensure_product(category):
    prod = Product.query.filter_by(slug="test-pos-product").first()
    if prod:
        return prod
    prod = Product(
        name="Test POS Product",
        slug="test-pos-product",
        sku_base="TEST-POS",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_public=True,
        is_pos_visible=True,
        base_price=Decimal("15.00"),
    )
    db.session.add(prod)
    db.session.flush()
    return prod


def _ensure_variant(product):
    variant = ProductVariant.query.filter_by(sku="TEST-POS-V1").first()
    if variant:
        return variant
    variant = ProductVariant(
        product=product,
        sku="TEST-POS-V1",
        name="Test Variant",
        price=Decimal("15.00"),
        active=True,
    )
    db.session.add(variant)
    db.session.flush()
    return variant


def _get_token(client):
    from app.models import User, UserRole
    from app.services.api_tokens import create_api_token

    with client.application.app_context():
        user = User.query.filter_by(email="test-token-user@example.com").first()
        if not user:
            user = User(
                email="test-token-user@example.com",
                first_name="Token",
                last_name="User",
                role=UserRole.ADMIN,
                is_active=True,
            )
            user.set_password("secret")
            db.session.add(user)
            db.session.commit()
        _, raw = create_api_token(user, "Test Token", scopes=["catalog"])
        return raw
