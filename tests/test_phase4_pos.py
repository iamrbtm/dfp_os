from __future__ import annotations

from decimal import Decimal

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
