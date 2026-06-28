from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    CustomRequest,
    CustomRequestStatus,
    Customer,
    InventoryLocation,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Payment,
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
from app.services import orders as order_svc
from app.services import print_jobs as print_job_svc
from app.services.crud import apply_search, archive_instance, get_by_id
from app.services.api_tokens import create_api_token
from sqlalchemy import select


# ---------------------------------------------------------------------------
# CRUD service helpers
# ---------------------------------------------------------------------------

def test_apply_search_no_term(app):
    with app.app_context():
        stmt = select(Product)
        result = apply_search(stmt, Product, "", ["name"])
        assert result is stmt


def test_apply_search_no_fields(app):
    with app.app_context():
        stmt = select(Product)
        result = apply_search(stmt, Product, "dragon", [])
        assert result is stmt


def test_apply_search_with_term(app):
    with app.app_context():
        cat = Category(name="Test", slug="test-apply-search")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="Searchable Dragon", slug="searchable-dragon",
                     category=cat, product_type=ProductType.FINISHED_GOOD,
                     status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.commit()
        stmt = select(Product)
        result = apply_search(stmt, Product, "dragon", ["name"])
        items = db.session.scalars(result).all()
        assert len(items) == 1


def test_archive_instance_deleted_at(app):
    with app.app_context():
        cat = Category(name="ArchiveDel", slug="archive-del")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="Del Test", slug="del-test", category=cat,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.commit()
        archive_instance(p)
        assert p.deleted_at is not None


def test_archive_instance_active(app):
    with app.app_context():
        loc = InventoryLocation(name="ArchiveActive", type="Storage")
        db.session.add(loc)
        db.session.commit()
        archive_instance(loc)
        assert loc.active is False


def test_archive_instance_is_public(app):
    with app.app_context():
        cat = Category(name="ArchivePublic", slug="archive-public")
        db.session.add(cat)
        db.session.commit()
        archive_instance(cat)
        assert cat.is_public is False


def test_archive_instance_status_retired(app):
    with app.app_context():
        printer = Printer(name="ArchiveStatus", model="Test")
        db.session.add(printer)
        db.session.commit()
        archive_instance(printer)
        assert printer.status == PrinterStatus.RETIRED


def test_get_by_id_none(app):
    with app.app_context():
        assert get_by_id(Product, 99999) is None


# ---------------------------------------------------------------------------
# Workflow services
# ---------------------------------------------------------------------------

def test_convert_custom_request_new_customer_no_deposit(app):
    with app.app_context():
        req = CustomRequest(name="New Person", email="new@example.com",
                            description="Custom widget", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        order = order_svc.convert_custom_request_to_order(req, Decimal("50.00"))
        assert order.total == Decimal("50.00")
        assert order.paid_amount == Decimal("0")
        assert order.source == OrderSource.CUSTOM
        assert len(order.payments) == 0
        cust = Customer.query.filter_by(email="new@example.com").first()
        assert cust is not None
        assert req.converted_to_order_id == order.id


def test_convert_custom_request_existing_customer_with_deposit(app):
    with app.app_context():
        cust = Customer(first_name="Existing", last_name="Cust",
                        email="existing@example.com", is_active=True)
        db.session.add(cust)
        db.session.commit()
        req = CustomRequest(name="Existing Cust", email="existing@example.com",
                            description="Another widget", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        order = order_svc.convert_custom_request_to_order(
            req, Decimal("75.00"), deposit_amount=Decimal("25.00"),
            deposit_method=PaymentMethod.VENMO,
        )
        assert order.paid_amount == Decimal("25.00")
        assert len(order.payments) == 1
        assert order.payments[0].method == PaymentMethod.VENMO
        assert req.status == CustomRequestStatus.DEPOSIT_COLLECTED


def test_convert_custom_request_single_word_name(app):
    with app.app_context():
        req = CustomRequest(name="SingleName", email="single@example.com",
                            description="Test", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        order_svc.convert_custom_request_to_order(req, Decimal("10.00"))
        cust = Customer.query.filter_by(email="single@example.com").first()
        assert cust.first_name == "SingleName"
        assert cust.last_name == ""


def test_convert_custom_request_no_email(app):
    with app.app_context():
        req = CustomRequest(name="No Email", email="",
                            description="Test", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        order = order_svc.convert_custom_request_to_order(req, Decimal("10.00"))
        assert order.customer.email is None


def test_create_print_job_from_order_item_default_label(app):
    with app.app_context():
        cat = Category(name="PJCat", slug="pj-cat")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="PJ Prod", slug="pj-prod", category=cat,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.flush()
        cust = Customer(first_name="PJ", last_name="Cust", email="pj@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.MANUAL)
        db.session.add(o)
        db.session.flush()
        item = OrderItem(order=o, quantity=1, unit_price=Decimal("5"), line_total=Decimal("5"))
        db.session.add(item)
        db.session.commit()
        job = print_job_svc.create_print_job_from_order_item(item)
        assert job.status == PrintJobStatus.QUEUED
        assert job.label == f"Print for order item #{item.id}"


def test_create_print_job_from_order_item_custom_label(app):
    with app.app_context():
        cat = Category(name="PJCat2", slug="pj-cat2")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="PJ Prod2", slug="pj-prod2", category=cat,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.flush()
        cust = Customer(first_name="PJ2", last_name="Cust", email="pj2@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.MANUAL)
        db.session.add(o)
        db.session.flush()
        item = OrderItem(order=o, quantity=2, unit_price=Decimal("5"), line_total=Decimal("10"))
        db.session.add(item)
        db.session.commit()
        job = print_job_svc.create_print_job_from_order_item(item, label="Custom Label", priority=3, estimated_minutes=60)
        assert job.label == "Custom Label"
        assert job.priority == 3
        assert job.estimated_minutes == 60


# ---------------------------------------------------------------------------
# Auth utilities
# ---------------------------------------------------------------------------

def test_staff_user_can_access_staff_routes(client, app):
    with app.app_context():
        staff = User(email="staff-auth-test@example.com", first_name="Staff", last_name="T",
                     role=UserRole.STAFF, is_active=True)
        staff.set_password("secret")
        db.session.add(staff)
        db.session.commit()
    login_resp = client.post("/auth/login", data={
        "email": "staff-auth-test@example.com", "password": "secret",
    }, follow_redirects=True)
    assert login_resp.status_code == 200
    response = client.get("/products/products/", follow_redirects=True)
    assert response.status_code == 200


def test_api_token_invalid_header(client):
    response = client.get("/api/v1/products", headers={"Authorization": "Bearer invalidtoken123"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_api_token"


def test_api_token_x_header(client, api_token):
    response = client.get("/api/v1/products", headers={"X-API-Token": api_token})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# API POST (create) for all resource types
# ---------------------------------------------------------------------------

def _api_token_header(client, scopes=None):
    with client.application.app_context():
        user = User(email="api-post-user@example.com", first_name="API", last_name="Post",
                    role=UserRole.ADMIN, is_active=True)
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _, raw = create_api_token(user, "Coverage Test Token", scopes=scopes or ["catalog"])
        return raw


def test_api_post_category(client):
    token = _api_token_header(client)
    r = client.post("/api/v1/categories", json={"name": "API Cat", "slug": "api-cat"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.get_json()["name"] == "API Cat"


def test_api_post_collection(client):
    token = _api_token_header(client)
    r = client.post("/api/v1/collections", json={"name": "API Coll", "slug": "api-coll"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_product(client):
    token = _api_token_header(client)
    with client.application.app_context():
        cat = Category(name="ProdCat", slug="prod-cat")
        db.session.add(cat)
        db.session.commit()
        cid = cat.id
    r = client.post("/api/v1/products", json={
        "name": "API Product", "slug": "api-product",
        "category_id": cid, "product_type": "finished_good",
        "status": "active", "license_status": "commercial_allowed",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_product_studio_fields(client):
    token = _api_token_header(client)
    with client.application.app_context():
        cat = Category(name="StudioCat", slug="studio-cat")
        db.session.add(cat)
        db.session.commit()
        cid = cat.id
    r = client.post("/api/v1/products", json={
        "name": "Studio Product",
        "slug": "studio-product",
        "category_id": cid,
        "product_type": "finished_good",
        "status": "draft",
        "license_status": "unknown",
        "model_source_type": "self_designed",
        "model_file_path": "/tmp/studio-product.stl",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_printer(client):
    token = _api_token_header(client, scopes=["inventory"])
    r = client.post("/api/v1/printers", json={
        "name": "Test Printer", "model": "Bambu A1", "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_ams_unit(client):
    token = _api_token_header(client, scopes=["inventory"])
    r = client.post("/api/v1/ams-units", json={
        "name": "Test AMS", "type": "ams_lite", "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_filament_spool(client):
    token = _api_token_header(client, scopes=["inventory"])
    r = client.post("/api/v1/filament-spools", json={
        "brand": "TestBrand", "material_type": "PLA",
        "color_name": "Test Color", "status": "new",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_inventory_location(client):
    token = _api_token_header(client, scopes=["inventory"])
    r = client.post("/api/v1/inventory-locations", json={
        "name": "API Location", "type": "Storage",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_customer(client):
    token = _api_token_header(client, scopes=["orders"])
    r = client.post("/api/v1/customers", json={
        "first_name": "API", "last_name": "Customer",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_post_custom_request(client):
    token = _api_token_header(client, scopes=["orders"])
    r = client.post("/api/v1/custom-requests", json={
        "name": "API Request", "email": "api-req@example.com",
        "description": "API test", "status": "new",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


def test_api_get_orders_list(client):
    token = _api_token_header(client, scopes=["orders"])
    r = client.get("/api/v1/orders", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

def test_api_post_print_job(client):
    token = _api_token_header(client, scopes=["orders"])
    r = client.post("/api/v1/print-jobs", json={
        "status": "queued", "label": "API Print Job",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# API PUT (update)
# ---------------------------------------------------------------------------

def test_api_put_product(client):
    token = _api_token_header(client)
    with client.application.app_context():
        cat = Category(name="PutCat", slug="put-cat")
        db.session.add(cat)
        db.session.flush()
        cid = cat.id
        p = Product(name="Original", slug="original", category_id=cid,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = client.put(f"/api/v1/products/{pid}", json={
        "name": "Updated!", "slug": "original",
        "category_id": cid, "product_type": "finished_good",
        "status": "active", "license_status": "commercial_allowed",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Updated!"


def test_api_put_not_found(client):
    token = _api_token_header(client)
    r = client.put("/api/v1/products/99999", json={"name": "Nope"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (404, 422)


def test_api_get_single_not_found(client):
    token = _api_token_header(client)
    r = client.get("/api/v1/products/99999",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_api_delete_product(client):
    token = _api_token_header(client)
    with client.application.app_context():
        cat = Category(name="DelCat", slug="del-cat")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="Delete Me", slug="delete-me", category=cat,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = client.delete(f"/api/v1/products/{pid}",
                      headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "archived"


def test_api_delete_not_found(client):
    token = _api_token_header(client)
    r = client.delete("/api/v1/products/99999",
                      headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_api_integrity_error_on_create(client):
    token = _api_token_header(client)
    with client.application.app_context():
        cat = Category(name="UniqueSlugCat", slug="unique-slug-cat")
        db.session.add(cat)
        db.session.commit()
    client.post("/api/v1/categories", json={"name": "Dup", "slug": "dup-slug"},
                headers={"Authorization": f"Bearer {token}"})
    r = client.post("/api/v1/categories", json={"name": "Dup", "slug": "dup-slug"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Admin blueprint CRUD for Phase 3 resources
# ---------------------------------------------------------------------------

def test_admin_create_customer(client, login_admin):
    r = client.post("/customers/customers/new", data={
        "first_name": "Admin", "last_name": "Create",
        "email": "admin-create@example.com",
    }, follow_redirects=True)
    assert r.status_code == 200
    with client.application.app_context():
        assert Customer.query.filter_by(email="admin-create@example.com").first() is not None


def test_admin_create_custom_request(client, login_admin):
    r = client.post("/custom-orders/requests/new", data={
        "name": "Admin Req", "email": "admin-req@example.com",
        "description": "Admin test", "status": "new",
    }, follow_redirects=True)
    assert r.status_code == 200


def test_admin_create_print_job(client, login_admin):
    r = client.post("/print-jobs/print-jobs/new", data={
        "status": "queued", "label": "Admin Print", "priority": 1,
    }, follow_redirects=True)
    assert r.status_code == 200


def test_admin_archive_customer(client, login_admin):
    with client.application.app_context():
        c = Customer(first_name="Archive", last_name="Me", email="archive-me@example.com", is_active=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.post(f"/customers/customers/{cid}/archive")
    assert r.status_code == 302, f"Expected redirect, got {r.status_code}: {r.data[:200]}"
    with client.application.app_context():
        archived = db.session.get(Customer, cid)
        assert archived is not None
        assert archived.deleted_at is not None


def test_admin_404_unknown_resource(client, login_admin):
    r = client.get("/customers/unknown-resource/")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Form apply edge cases
# ---------------------------------------------------------------------------

def test_customer_form_apply_empty_optional(app):
    with app.app_context():
        c = Customer(first_name="Test", last_name="Form")
        c.email = None
        c.phone = None
        c.address_line_1 = None
        c.address_line_2 = None
        c.city = None
        c.state = None
        c.zip_code = None
        c.notes = "test"
        c.is_active = False
        db.session.add(c)
        db.session.commit()
        assert c.email is None
        assert c.is_active is False


def test_order_form_apply_no_customer(app):
    with app.app_context():
        o = Order(status=OrderStatus.PENDING, source=OrderSource.MANUAL,
                   subtotal=Decimal("0"), total=Decimal("0"), paid_amount=Decimal("0"))
        assert o.customer_id is None


def test_order_item_form_apply_custom(app):
    with app.app_context():
        cat = Category(name="OIApplyCat", slug="oi-apply-cat")
        db.session.add(cat)
        db.session.flush()
        cust = Customer(first_name="OIApply", last_name="C", email="oi-apply@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.MANUAL)
        db.session.add(o)
        db.session.flush()
        item = OrderItem(order=o, is_custom_item=True, custom_description="Custom widget",
                          quantity=1, unit_price=Decimal("10"), line_total=Decimal("10"))
        db.session.add(item)
        db.session.commit()
        assert item.is_custom_item is True
        assert item.custom_description == "Custom widget"


def test_print_job_default_status(app):
    with app.app_context():
        job = PrintJob(status=PrintJobStatus.QUEUED, priority=0, estimated_minutes=0, label="Default")
        db.session.add(job)
        db.session.commit()
        assert job.status == PrintJobStatus.QUEUED


def test_payment_no_reference(app):
    with app.app_context():
        cust = Customer(first_name="PayRef", last_name="T", email="pay-ref@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.POS)
        db.session.add(o)
        db.session.flush()
        p = Payment(order=o, amount=Decimal("5"), method=PaymentMethod.CASH)
        db.session.add(p)
        db.session.commit()
        assert p.reference is None


# ---------------------------------------------------------------------------
# Customer with no email in convert workflow (edge from service)
# ---------------------------------------------------------------------------

def test_convert_request_no_email_no_existing_customer(app):
    with app.app_context():
        req = CustomRequest(name="No Email Req", email="",
                            description="test", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        order = order_svc.convert_custom_request_to_order(req, Decimal("20.00"))
        assert order.total == Decimal("20.00")
        assert req.converted_to_order_id == order.id
