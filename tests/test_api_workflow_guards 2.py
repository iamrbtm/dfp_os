from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    InventoryLocation,
    InventoryRecord,
    PosSale,
    PosSaleStatus,
    PosSession,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.models.receipt import Receipt, ReceiptStatus
from app.services.api_tokens import create_api_token


def _api_headers(scopes: list[str]) -> dict[str, str]:
    user = User(
        email=f"workflow-{','.join(scopes)}@example.com",
        first_name="Workflow",
        last_name="Guard",
        role=UserRole.ADMIN,
        is_active=True,
    )
    user.set_password("super-secret")
    db.session.add(user)
    db.session.commit()
    _token, raw = create_api_token(user=user, name="Workflow Guard", scopes=scopes)
    return {"Authorization": f"Bearer {raw}"}


def _product_and_location() -> tuple[Product, InventoryLocation]:
    category = Category(name="Guard Category", slug="guard-category", is_public=True, is_pos_visible=True)
    product = Product(
        name="Guard Product",
        slug="guard-product",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_pos_visible=True,
        base_price=Decimal("12.00"),
    )
    location = InventoryLocation(name="Guard Bin", type="Bin", active=True)
    db.session.add_all([category, product, location])
    db.session.commit()
    return product, location


def test_generic_api_cannot_directly_change_inventory_quantities(client):
    with client.application.app_context():
        headers = _api_headers(["inventory"])
        product, location = _product_and_location()
        record = InventoryRecord(
            product_id=product.id,
            location_id=location.id,
            quantity_on_hand=5,
            quantity_reserved=0,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id
        product_id = product.id
        location_id = location.id

    response = client.put(
        f"/api/v1/inventory-records/{record_id}",
        json={"product_id": product_id, "location_id": location_id, "quantity_on_hand": 99},
        headers=headers,
    )

    assert response.status_code == 400
    with client.application.app_context():
        assert db.session.get(InventoryRecord, record_id).quantity_on_hand == 5


def test_generic_api_cannot_approve_receipt(client):
    with client.application.app_context():
        headers = _api_headers(["receipts"])
        user = User(
            email="receipt-workflow@example.com",
            first_name="Receipt",
            last_name="Owner",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        receipt = Receipt(user_id=user.id, status=ReceiptStatus.NEEDS_REVIEW, merchant_name="Store")
        db.session.add(receipt)
        db.session.commit()
        receipt_id = receipt.id

    response = client.put(
        f"/api/v1/receipts/{receipt_id}",
        json={"status": "approved", "merchant_name": "Store"},
        headers=headers,
    )

    assert response.status_code == 400
    with client.application.app_context():
        assert db.session.get(Receipt, receipt_id).status == ReceiptStatus.NEEDS_REVIEW


def test_generic_api_cannot_change_pos_sale_status(client):
    with client.application.app_context():
        headers = _api_headers(["pos"])
        user = User(
            email="pos-workflow@example.com",
            first_name="POS",
            last_name="Owner",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        session = PosSession(opened_by_user_id=user.id, opening_cash=Decimal("0.00"))
        db.session.add(session)
        db.session.flush()
        sale = PosSale(
            pos_session_id=session.id,
            subtotal=Decimal("10.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("10.00"),
            payment_method="cash",
            amount_received=Decimal("10.00"),
            change_due=Decimal("0.00"),
            status=PosSaleStatus.COMPLETED,
        )
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id

    response = client.put(
        f"/api/v1/pos-sales/{sale_id}",
        json={"payment_method": "cash", "total": "10.00", "amount_received": "10.00", "status": "refunded"},
        headers=headers,
    )

    assert response.status_code in {400, 422}
    with client.application.app_context():
        assert db.session.get(PosSale, sale_id).status == PosSaleStatus.COMPLETED
