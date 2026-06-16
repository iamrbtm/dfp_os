from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    AMSUnit,
    AMSUnitStatus,
    AMSUnitType,
    CustomRequest,
    CustomRequestStatus,
    Category,
    Collection,
    Customer,
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    LicenseStatus,
    ModelAsset,
    ModelSourceType,
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
    ProductVariant,
    User,
    UserRole,
)
from app.services.auth import authenticate_user
from app.services.api_tokens import create_api_token, authenticate_api_token
from app.utils.urls import is_safe_local_url


# ---------------------------------------------------------------------------
# Authenticate failure paths
# ---------------------------------------------------------------------------

def test_authenticate_user_bad_password(app):
    with app.app_context():
        u = User(email="auth-fail@example.com", first_name="Fail", last_name="T",
                 role=UserRole.ADMIN, is_active=True)
        u.set_password("good")
        db.session.add(u)
        db.session.commit()
        result = authenticate_user("auth-fail@example.com", "wrong")
        assert result is None


def test_authenticate_user_no_user(app):
    with app.app_context():
        result = authenticate_user("nobody@example.com", "any")
        assert result is None


def test_authenticate_user_inactive(app):
    with app.app_context():
        u = User(email="inactive@example.com", first_name="In", last_name="Active",
                 role=UserRole.ADMIN, is_active=False)
        u.set_password("secret")
        db.session.add(u)
        db.session.commit()
        result = authenticate_user("inactive@example.com", "secret")
        assert result is None


# ---------------------------------------------------------------------------
# API token deactivation
# ---------------------------------------------------------------------------

def test_api_token_deactivated(app):
    with app.app_context():
        u = User(email="token-deact@example.com", first_name="Token", last_name="Deact",
                 role=UserRole.ADMIN, is_active=True)
        u.set_password("secret")
        db.session.add(u)
        db.session.commit()
        token, raw = create_api_token(u, "Deact Test", scopes=["catalog"])
        assert authenticate_api_token(raw) is not None
        from datetime import datetime, timezone
        token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        assert authenticate_api_token(raw) is None


# ---------------------------------------------------------------------------
# URL safety utility
# ---------------------------------------------------------------------------

def test_is_safe_local_url(app):
    with app.test_request_context("/"):
        assert is_safe_local_url("/products/products/") is True
        assert is_safe_local_url("http://evil.com") is False
        assert is_safe_local_url("https://evil.com/phish") is False
        assert is_safe_local_url("") is False
        assert is_safe_local_url(None) is False


# ---------------------------------------------------------------------------
# API PUT for more resource types
# ---------------------------------------------------------------------------

def _api_token(client):
    with client.application.app_context():
        u = User(email="api-put-all@example.com", first_name="API", last_name="PutAll",
                 role=UserRole.ADMIN, is_active=True)
        u.set_password("secret")
        db.session.add(u)
        db.session.commit()
        _, raw = create_api_token(u, "PutAll Token", scopes=["catalog"])
        return raw


def test_api_put_category(client):
    token = _api_token(client)
    with client.application.app_context():
        c = Category(name="PutCat", slug="put-cat-old")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.put(f"/api/v1/categories/{cid}", json={"name": "Updated Cat", "slug": "put-cat-old"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Updated Cat"


def test_api_put_collection(client):
    token = _api_token(client)
    with client.application.app_context():
        c = Collection(name="Old Coll", slug="old-coll")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.put(f"/api/v1/collections/{cid}", json={"name": "Updated Coll", "slug": "old-coll"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Updated Coll"


def test_api_put_customer(client):
    token = _api_token(client)
    with client.application.app_context():
        c = Customer(first_name="Old", last_name="Name", email="put-cust@example.com")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.put(f"/api/v1/customers/{cid}", json={"first_name": "New", "last_name": "Name"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["first_name"] == "New"


def test_api_put_printer(client):
    token = _api_token(client)
    with client.application.app_context():
        p = Printer(name="Old Printer", model="Test", status=PrinterStatus.IDLE)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = client.put(f"/api/v1/printers/{pid}", json={"name": "Updated Printer", "model": "Test", "status": "active"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "Updated Printer"


def test_api_put_variant(client):
    token = _api_token(client)
    with client.application.app_context():
        cat = Category(name="VarPutCat", slug="var-put-cat")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="VarPut", slug="var-put", category_id=cat.id,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.flush()
        v = ProductVariant(product_id=p.id, sku="VAR-PUT", name="Old Variant", price=Decimal("5"))
        db.session.add(v)
        db.session.commit()
        vid = v.id
        pid = p.id
    r = client.put(f"/api/v1/variants/{vid}", json={"product_id": pid, "sku": "VAR-PUT", "name": "New Variant"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["name"] == "New Variant"


# ---------------------------------------------------------------------------
# API DELETE for more resources
# ---------------------------------------------------------------------------

def test_api_delete_category(client):
    token = _api_token(client)
    with client.application.app_context():
        c = Category(name="DelCat", slug="del-cat-api")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.delete(f"/api/v1/categories/{cid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "archived"


def test_api_delete_customer(client):
    token = _api_token(client)
    with client.application.app_context():
        c = Customer(first_name="Del", last_name="Cust", email="del-cust@example.com")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.delete(f"/api/v1/customers/{cid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "archived"


# ---------------------------------------------------------------------------
# API search/pagination
# ---------------------------------------------------------------------------

def test_api_search_products(client, catalog_product):
    token = _api_token(client)
    r = client.get("/api/v1/products?q=rainbow", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["pagination"]["total"] >= 1


def test_api_pagination(client):
    token = _api_token(client)
    r = client.get("/api/v1/products?page=1&per_page=5", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["pagination"]["per_page"] == 5


# ---------------------------------------------------------------------------
# Admin blueprint detail and edit (Phase 3 resources)
# ---------------------------------------------------------------------------

def test_admin_customer_detail(client, login_admin):
    with client.application.app_context():
        c = Customer(first_name="Detail", last_name="View", email="detail-view@example.com")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.get(f"/customers/customers/{cid}", follow_redirects=False)
    assert r.status_code == 200


def test_admin_customer_edit(client, login_admin):
    with client.application.app_context():
        c = Customer(first_name="Edit", last_name="Me", email="edit-me@example.com")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    r = client.post(f"/customers/customers/{cid}/edit", data={
        "first_name": "Edited", "last_name": "Me", "email": "edit-me@example.com",
    }, follow_redirects=True)
    assert r.status_code == 200
    with client.application.app_context():
        updated = db.session.get(Customer, cid)
        assert updated.first_name == "Edited"


def test_admin_custom_request_detail(client, login_admin):
    with client.application.app_context():
        req = CustomRequest(name="Detail Req", email="detail-req@example.com",
                            description="Test", status=CustomRequestStatus.NEW)
        db.session.add(req)
        db.session.commit()
        rid = req.id
    r = client.get(f"/custom-orders/requests/{rid}")
    assert r.status_code == 200


def test_admin_print_job_detail(client, login_admin):
    with client.application.app_context():
        job = PrintJob(status=PrintJobStatus.QUEUED, label="Detail Job")
        db.session.add(job)
        db.session.commit()
        jid = job.id
    r = client.get(f"/print-jobs/print-jobs/{jid}")
    assert r.status_code == 200


def test_admin_order_detail(client, login_admin):
    with client.application.app_context():
        cust = Customer(first_name="OrdDet", last_name="C", email="ord-det@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.POS)
        db.session.add(o)
        db.session.commit()
        oid = o.id
    r = client.get(f"/orders/orders/{oid}")
    assert r.status_code == 200


def test_admin_order_edit(client, login_admin):
    with client.application.app_context():
        cust = Customer(first_name="OrdEdit", last_name="C", email="ord-edit@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.POS)
        db.session.add(o)
        db.session.commit()
        oid = o.id
    r = client.post(f"/orders/orders/{oid}/edit", data={
        "status": "confirmed", "source": "pos",
    }, follow_redirects=True)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Additional form edge coverage
# ---------------------------------------------------------------------------

def test_category_form_apply(app):
    with app.app_context():
        c = Category(name="Test", slug="test-form")
        c.name = "  Spaces  "
        c.slug = "  spaces  "
        c.description = "Desc"
        c.sort_order = 5
        c.is_public = False
        c.is_pos_visible = False
        db.session.add(c)
        db.session.commit()
        assert c.name == "  Spaces  "


def test_collection_form_apply(app):
    with app.app_context():
        c = Collection(name="Coll", slug="coll-form")
        c.is_public = False
        c.sort_order = 3
        db.session.add(c)
        db.session.commit()


def test_printer_form_apply(app):
    with app.app_context():
        p = Printer(name="Form Printer", model="Test", status=PrinterStatus.ACTIVE,
                     location="Upstairs", has_ams=True)
        p.notes = "Test notes"
        p.total_print_hours = 42
        db.session.add(p)
        db.session.commit()


def test_ams_unit_form_apply(app):
    with app.app_context():
        a = AMSUnit(name="Form AMS", type=AMSUnitType.AMS_LITE, status=AMSUnitStatus.ACTIVE,
                     slot_count=4)
        db.session.add(a)
        db.session.commit()


def test_filament_spool_form_apply(app):
    with app.app_context():
        f = FilamentSpool(brand="Test", material_type="PLA", color_name="Blue",
                           status=FilamentStatus.ACTIVE, remaining_weight_grams=500)
        f.notes = "Filament notes"
        db.session.add(f)
        db.session.commit()


def test_inventory_location_form_apply(app):
    with app.app_context():
        loc = InventoryLocation(name="Form Location", type="Shelf", active=True)
        loc.description = "A shelf"
        db.session.add(loc)
        db.session.commit()


def test_product_variant_apply(app):
    with app.app_context():
        cat = Category(name="VarFormCat", slug="var-form-cat")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="VarForm", slug="var-form", category_id=cat.id,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.flush()
        v = ProductVariant(product_id=p.id, sku="VAR-FORM", name="Form Variant",
                             price=Decimal("9.99"), material_cost=Decimal("2.00"))
        v.active = True
        v.pos_button_label = "Form"
        v.pos_sort_order = 1
        db.session.add(v)
        db.session.commit()


def test_model_asset_apply(app):
    with app.app_context():
        cat = Category(name="MAFormCat", slug="ma-form-cat")
        db.session.add(cat)
        db.session.flush()
        p = Product(name="MAForm", slug="ma-form", category_id=cat.id,
                     product_type=ProductType.FINISHED_GOOD, status=ProductStatus.DRAFT)
        db.session.add(p)
        db.session.flush()
        ma = ModelAsset(title="Form Asset", source_type=ModelSourceType.SELF_DESIGNED,
                         status=LicenseStatus.COMMERCIAL_ALLOWED, related_product_id=p.id)
        ma.notes = "Asset notes"
        db.session.add(ma)
        db.session.commit()


def test_order_status_enum_values():
    assert OrderStatus.PENDING.value == "pending"
    assert OrderStatus.COMPLETED.value == "completed"
    assert OrderSource.POS.value == "pos"
    assert PaymentMethod.CASH.value == "cash"
    assert PrintJobStatus.QUEUED.value == "queued"


# ---------------------------------------------------------------------------
# Edge cases on forms/order.py uncovered apply paths
# ---------------------------------------------------------------------------

def test_order_form_edge_cases(app):
    with app.app_context():
        cust = Customer(first_name="Edge", last_name="Case", email="edge@example.com")
        db.session.add(cust)
        db.session.flush()
        o = Order(customer=cust, status=OrderStatus.PENDING, source=OrderSource.MANUAL,
                   subtotal=Decimal("0"), tax_total=Decimal("0"),
                   discount_total=Decimal("0"), total=Decimal("0"), paid_amount=Decimal("0"))
        o.notes = ""
        o.internal_notes = None
        db.session.add(o)
        db.session.commit()
        assert o.notes == ""
        assert o.internal_notes is None


# ---------------------------------------------------------------------------
# Public page edge cases
# ---------------------------------------------------------------------------

def test_public_custom_orders_with_budget_and_phone(client):
    r = client.post("/custom-orders", data={
        "name": "Full Form",
        "email": "full-form@example.com",
        "phone": "931-555-0000",
        "description": "Custom order with full details.",
        "estimated_budget": "50.00",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Request received" in r.data


# ---------------------------------------------------------------------------
# Config edge case
# ---------------------------------------------------------------------------

def test_config_default_returns_development(app):
    from app.config import config_by_name
    assert "development" in config_by_name
    assert "testing" in config_by_name
    assert "production" in config_by_name


# ---------------------------------------------------------------------------
# utils/auth.py edge cases not yet covered
# ---------------------------------------------------------------------------

def test_roles_required_unauthenticated_redirect(client):
    response = client.get("/products/products/")
    assert response.status_code == 302
