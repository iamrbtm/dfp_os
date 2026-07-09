from __future__ import annotations

from decimal import Decimal

import httpx

from app.extensions import db
from app.models import (
    Category,
    InventoryLocation,
    InventoryRecord,
    PosSaleStatus,
    PosSessionStatus,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.audit_client import AuditClient, AuditDispatchError
from app.services.pos import close_session, create_sale, get_session_summary, open_session, refund_sale, void_session


def _ensure_admin_id(app):
    with app.app_context():
        user = User.query.filter_by(email="pos-admin@example.com").first()
        if not user:
            user = User(
                email="pos-admin@example.com",
                first_name="POS",
                last_name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            user.set_password("super-secret")
            db.session.add(user)
            db.session.commit()
        return user.id


def _ensure_product():
    category = Category.query.filter_by(slug="pos-test-cat").first()
    if not category:
        category = Category(name="POS Test", slug="pos-test-cat", is_public=True, is_pos_visible=True)
        db.session.add(category)
        db.session.flush()
    product = Product.query.filter_by(slug="pos-test-prod").first()
    if not product:
        product = Product(
            name="POS Test Product",
            slug="pos-test-prod",
            category_id=category.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_pos_visible=True,
            base_price=Decimal("10.00"),
        )
        db.session.add(product)
        db.session.flush()
    return product


def _ensure_location():
    location = InventoryLocation.query.filter_by(name="Test POS Bin").first()
    if not location:
        location = InventoryLocation(name="Test POS Bin", type="Bin", active=True)
        db.session.add(location)
        db.session.flush()
    return location


def test_pos_open_and_close_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        location = _ensure_location()
        session = open_session(
            user_id=admin_id,
            opening_cash=Decimal("50.00"),
            inventory_location_id=location.id,
            notes="Test session",
        )
        assert session.status == PosSessionStatus.OPEN

        closed = close_session(session.id, admin_id, Decimal("50.00"))
        assert closed.status == PosSessionStatus.CLOSED
        assert closed.closed_by_user_id == admin_id


def test_pos_void_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        void_session(session.id)
        assert session.status == PosSessionStatus.VOIDED


def test_pos_create_sale_deducts_product_inventory(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        location = _ensure_location()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                location_id=location.id,
                quantity_on_hand=3,
                quantity_reserved=0,
            )
        )
        db.session.commit()

        session = open_session(user_id=admin_id, opening_cash=Decimal("50.00"), inventory_location_id=location.id)
        sale, order = create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("20.00"),
            items=[
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "unit_price": "10.00",
                    "description": "Test Product",
                    "item_type": "product",
                }
            ],
        )

        assert sale.total == Decimal("10.00")
        assert sale.status == PosSaleStatus.COMPLETED
        assert order.total == Decimal("10.00")
        inventory = InventoryRecord.query.filter_by(product_id=product.id, location_id=location.id).first()
        assert inventory.quantity_on_hand == 2


def test_pos_uses_database_price_when_client_price_is_tampered(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        location = _ensure_location()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                location_id=location.id,
                quantity_on_hand=3,
                quantity_reserved=0,
            )
        )
        db.session.commit()

        session = open_session(user_id=admin_id, opening_cash=Decimal("0"), inventory_location_id=location.id)
        sale, order = create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("10.00"),
            items=[
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "unit_price": "0.01",
                    "description": "Tampered Product",
                    "item_type": "product",
                }
            ],
        )

        assert sale.total == Decimal("10.00")
        assert order.total == Decimal("10.00")
        assert sale.items[0].unit_price == Decimal("10.00")


def test_pos_rejects_negative_quantity(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))

        try:
            create_sale(
                session_id=session.id,
                payment_method="cash",
                amount_received=Decimal("10.00"),
                items=[
                    {
                        "product_id": product.id,
                        "quantity": -1,
                        "unit_price": "10.00",
                        "item_type": "product",
                    }
                ],
            )
        except ValueError as exc:
            assert "Quantity must be greater than zero" in str(exc)
        else:
            raise AssertionError("Negative quantity was accepted")


def test_pos_rejects_negative_discount(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))

        try:
            create_sale(
                session_id=session.id,
                payment_method="cash",
                amount_received=Decimal("10.00"),
                items=[
                    {
                        "quantity": 1,
                        "unit_price": "10.00",
                        "discount_amount": "-1.00",
                        "description": "Custom item",
                        "item_type": "custom_item",
                    }
                ],
            )
        except ValueError as exc:
            assert "Discount cannot be negative" in str(exc)
        else:
            raise AssertionError("Negative discount was accepted")


def test_pos_rejects_negative_tax(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))

        try:
            create_sale(
                session_id=session.id,
                payment_method="cash",
                amount_received=Decimal("10.00"),
                tax_total=Decimal("-0.01"),
                items=[
                    {
                        "quantity": 1,
                        "unit_price": "10.00",
                        "description": "Custom item",
                        "item_type": "custom_item",
                    }
                ],
            )
        except ValueError as exc:
            assert "Tax total cannot be negative" in str(exc)
        else:
            raise AssertionError("Negative tax was accepted")


def test_pos_rejects_insufficient_cash(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))

        try:
            create_sale(
                session_id=session.id,
                payment_method="cash",
                amount_received=Decimal("9.99"),
                items=[
                    {
                        "product_id": product.id,
                        "quantity": 1,
                        "unit_price": "10.00",
                        "item_type": "product",
                    }
                ],
            )
        except ValueError as exc:
            assert "Cash received must cover the sale total" in str(exc)
        else:
            raise AssertionError("Insufficient cash was accepted")


def test_pos_custom_item_and_summary(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        create_sale(
            session_id=session.id,
            payment_method="venmo",
            amount_received=Decimal("25.00"),
            items=[
                {
                    "quantity": 1,
                    "unit_price": "25.00",
                    "description": "Custom keychain",
                    "item_type": "custom_item",
                }
            ],
        )
        summary = get_session_summary(session.id)
        assert summary["sale_count"] == 1
        assert summary["payment_totals"]["venmo"] == Decimal("25.00")


def test_pos_refund_sale_restocks_inventory(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        location = _ensure_location()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                location_id=location.id,
                quantity_on_hand=3,
                quantity_reserved=0,
            )
        )
        db.session.commit()

        session = open_session(user_id=admin_id, opening_cash=Decimal("20.00"), inventory_location_id=location.id)
        sale, _order = create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("10.00"),
            items=[
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "unit_price": "10.00",
                    "description": "Refund Product",
                    "item_type": "product",
                }
            ],
        )

        refunded = refund_sale(sale_id=sale.id, actor_id=admin_id, restock=True)
        assert refunded.status == PosSaleStatus.REFUNDED
        inventory = InventoryRecord.query.filter_by(product_id=product.id, location_id=location.id).first()
        assert inventory.quantity_on_hand == 3


def test_pos_sale_fails_closed_when_critical_audit_fails(app, monkeypatch):
    class FailingAuditClient:
        def record(self, **kwargs):
            if kwargs.get("critical"):
                raise AuditDispatchError("audit down")
            return None

    with app.app_context():
        app.config["AUDIT_LOG_ENABLED"] = True
        app.config["AUDIT_LOG_FAIL_CLOSED"] = True
        monkeypatch.setattr("app.services.audit.get_audit_client", lambda: FailingAuditClient())
        admin_id = _ensure_admin_id(app)
        product = _ensure_product()
        location = _ensure_location()
        db.session.add(
            InventoryRecord(
                product_id=product.id,
                location_id=location.id,
                quantity_on_hand=3,
                quantity_reserved=0,
            )
        )
        db.session.commit()
        session = open_session(user_id=admin_id, opening_cash=Decimal("0"), inventory_location_id=location.id)

        try:
            create_sale(
                session_id=session.id,
                payment_method="cash",
                amount_received=Decimal("10.00"),
                items=[
                    {
                        "product_id": product.id,
                        "quantity": 1,
                        "unit_price": "10.00",
                        "item_type": "product",
                    }
                ],
            )
        except AuditDispatchError:
            pass
        else:
            raise AssertionError("Critical audit failure did not block POS sale")

        inventory = InventoryRecord.query.filter_by(product_id=product.id, location_id=location.id).first()
        assert inventory.quantity_on_hand == 3


def test_critical_audit_failure_does_not_raise_when_fail_closed_is_disabled(app, monkeypatch):
    class FailingHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, *args, **kwargs):
            raise httpx.RequestError("audit down")

    with app.app_context():
        app.config["AUDIT_LOG_FAIL_CLOSED"] = False
        monkeypatch.setattr("app.services.audit_client.httpx.Client", FailingHttpClient)
        client = AuditClient(base_url="http://audit-log", token="token", enabled=True)

        assert client.record(action="x.y", entity_type="thing", critical=True) is None
