from __future__ import annotations


from app.extensions import db
from app.models import (
    AMSUnit,
    AMSUnitStatus,
    AMSUnitType,
    Category,
    Collection,
    Customer,
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    Order,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    Printer,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.api_tokens import authenticate_api_token, create_api_token
from app.services.auth import authenticate_user
from app.utils.urls import is_safe_local_url


def test_authenticate_user_failure_paths(app):
    with app.app_context():
        user = User(email="auth-fail@example.com", first_name="Fail", last_name="T", role=UserRole.ADMIN, is_active=True)
        user.set_password("good")
        db.session.add(user)
        db.session.commit()
        assert authenticate_user("auth-fail@example.com", "wrong") is None
        assert authenticate_user("nobody@example.com", "any") is None


def test_api_token_revocation(app):
    from datetime import datetime, timezone

    with app.app_context():
        user = User(email="token-deact@example.com", first_name="Token", last_name="Deact", role=UserRole.ADMIN, is_active=True)
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user, "Deact Test", scopes=["catalog"])
        assert authenticate_api_token(raw) is not None
        token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        assert authenticate_api_token(raw) is None


def test_safe_local_url(app):
    with app.test_request_context("/"):
        assert is_safe_local_url("/products/studio") is True
        assert is_safe_local_url("http://evil.com") is False


def _api_token(client):
    with client.application.app_context():
        user = User(email="api-put-all@example.com", first_name="API", last_name="PutAll", role=UserRole.ADMIN, is_active=True)
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _, raw = create_api_token(user, "PutAll Token", scopes=["catalog"])
        return raw


def test_api_put_category_collection_and_product(client):
    token = _api_token(client)
    with client.application.app_context():
        category = Category(name="PutCat", slug="put-cat-old")
        collection = Collection(name="Old Coll", slug="old-coll")
        db.session.add_all([category, collection])
        db.session.flush()
        product = Product(
            name="Put Product",
            slug="put-product",
            category_id=category.id,
            collection_id=collection.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.DRAFT,
            model_file_path="/tmp/model.stl",
        )
        db.session.add(product)
        db.session.commit()
        category_id = category.id
        collection_id = collection.id
        product_id = product.id

    assert client.put(f"/api/v1/categories/{category_id}", json={"name": "Updated Cat", "slug": "put-cat-old"}, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.put(f"/api/v1/collections/{collection_id}", json={"name": "Updated Coll", "slug": "old-coll"}, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    product_response = client.put(
        f"/api/v1/products/{product_id}",
        json={
            "name": "Updated Product",
            "slug": "put-product",
            "category_id": category_id,
            "collection_id": collection_id,
            "product_type": "finished_good",
            "status": "draft",
            "license_status": "unknown",
            "model_source_type": "self_designed",
            "model_file_path": "/tmp/updated.stl",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert product_response.status_code == 200
    assert product_response.get_json()["name"] == "Updated Product"


def test_admin_detail_pages_and_basic_model_persistence(client, login_admin, app):
    with app.app_context():
        customer = Customer(first_name="Detail", last_name="View", email="detail-view@example.com")
        printer = Printer(name="Form Printer", model="Test", status=PrinterStatus.ACTIVE, location="Upstairs", has_ams=True)
        ams = AMSUnit(name="Form AMS", type=AMSUnitType.AMS_LITE, status=AMSUnitStatus.ACTIVE, slot_count=4)
        spool = FilamentSpool(brand="Test", material_type="PLA", color_name="Blue", status=FilamentStatus.ACTIVE, remaining_weight_grams=500)
        inventory_location = InventoryLocation(name="Form Location", type="Shelf", active=True)
        order = Order(status=OrderStatus.PENDING, source=OrderSource.POS)
        job = PrintJob(status=PrintJobStatus.QUEUED, label="Detail Job")
        db.session.add_all([customer, printer, ams, spool, inventory_location, order, job])
        db.session.commit()

        assert customer.id is not None
        assert printer.id is not None
        assert ams.id is not None
        assert spool.id is not None
        customer_id = customer.id
        order_id = order.id
        job_id = job.id

    assert client.get(f"/customers/customers/{customer_id}", follow_redirects=False).status_code == 200
    assert client.get(f"/orders/orders/{order_id}", follow_redirects=False).status_code == 200
    assert client.get(f"/print-jobs/print-jobs/{job_id}", follow_redirects=False).status_code == 200


def test_enum_values_and_payment_method_constants():
    assert OrderStatus.PENDING.value == "pending"
    assert OrderSource.POS.value == "pos"
    assert PaymentMethod.CASH.value == "cash"
    assert PrintJobStatus.QUEUED.value == "queued"
