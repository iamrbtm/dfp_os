from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Receipt,
    ReceiptLineItem,
    ReceiptLineAllocation,
    ReceiptStatus,
    User,
    UserRole,
    Expense,
)
from app.models.receipt import (
    AllocationType,
)
from app.services.receipts import approve_receipt, reject_receipt, get_receipt_dashboard
from app.services.receipt_allocations import allocate_taxes_and_fees, set_line_allocation, bulk_assign_line_items, get_reconciliation_summary
from app.services.receipt_duplicates import check_duplicates, resolve_duplicate


@pytest.fixture()
def app_with_receipts(tmp_path):
    database_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"
    receipt_path = tmp_path / "receipts"

    app = create_app(
        "testing",
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(upload_path),
            "RECEIPT_STORAGE_PATH": str(receipt_path),
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "change-me-now",
            "SERVER_NAME": "localhost.localdomain",
            "WTF_CSRF_ENABLED": False,
            "AUDIT_LOG_ENABLED": False,
        },
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def admin_user(app_with_receipts):
    with app_with_receipts.app_context():
        user = User(
            email="admin@test.com",
            first_name="Admin",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        return {
            "id": user.id,
            "email": user.email,
            "password": "password",
        }


@pytest.fixture()
def sample_receipt(app_with_receipts, admin_user):
    with app_with_receipts.app_context():
        receipt = Receipt(
            user_id=admin_user["id"],
            status=ReceiptStatus.UPLOADED,
            merchant_name="Test Store",
            store_name="Test Store #1",
            receipt_number="RCP-001",
            date_time=datetime(2026, 5, 15, 14, 30, tzinfo=timezone.utc),
            subtotal=Decimal("100.00"),
            tax_total=Decimal("8.00"),
            grand_total=Decimal("108.00"),
            payment_method="credit",
            currency="USD",
            file_hash="abc123",
        )
        db.session.add(receipt)
        db.session.flush()

        items = [
            ("Widget A", "SKU-A", 2, Decimal("10.00"), Decimal("20.00"), "taxable"),
            ("Widget B", "SKU-B", 1, Decimal("30.00"), Decimal("30.00"), "taxable"),
            ("Widget C", "SKU-C", 5, Decimal("5.00"), Decimal("25.00"), "non_taxable"),
            ("Widget D", "SKU-D", 3, Decimal("8.33"), Decimal("25.00"), "unknown"),
        ]
        for i, (desc, sku, qty, price, total, taxable) in enumerate(items):
            item = ReceiptLineItem(
                receipt_id=receipt.id,
                row_order=i,
                description=desc,
                sku=sku,
                quantity=qty,
                unit_price=price,
                line_subtotal=total,
                line_total=total,
                taxable_status=taxable,
                needs_review=True,
            )
            db.session.add(item)

        db.session.commit()
        return receipt.id


@pytest.fixture()
def client(app_with_receipts, admin_user):
    client = app_with_receipts.test_client()
    with app_with_receipts.app_context():
        client.post(
            "/auth/login",
            data={"email": admin_user["email"], "password": admin_user["password"]},
        )
    return client


class TestReceiptModel:
    def test_create_receipt(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
                merchant_name="Test Merchant",
                grand_total=Decimal("50.00"),
            )
            db.session.add(receipt)
            db.session.commit()
            assert receipt.id is not None
            assert receipt.status == ReceiptStatus.UPLOADED
            assert receipt.merchant_name == "Test Merchant"
            assert receipt.grand_total == Decimal("50.00")

    def test_create_line_items(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
            )
            db.session.add(receipt)
            db.session.flush()

            item = ReceiptLineItem(
                receipt_id=receipt.id,
                row_order=0,
                description="Test Item",
                quantity=Decimal("2"),
                unit_price=Decimal("10.00"),
                line_total=Decimal("20.00"),
            )
            db.session.add(item)
            db.session.commit()
            assert item.id is not None
            assert len(receipt.line_items) == 1

    def test_create_allocation(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(user_id=admin_user["id"], status=ReceiptStatus.UPLOADED)
            db.session.add(receipt)
            db.session.flush()

            item = ReceiptLineItem(receipt_id=receipt.id, row_order=0, description="Item")
            db.session.add(item)
            db.session.flush()

            alloc = ReceiptLineAllocation(
                receipt_line_item_id=item.id,
                allocation_type=AllocationType.MARKET,
                amount=Decimal("10.00"),
                percent=Decimal("100"),
            )
            db.session.add(alloc)
            db.session.commit()
            assert alloc.id is not None
            assert alloc.allocation_type == AllocationType.MARKET


class TestReceiptServices:
    def test_get_dashboard_empty(self, app_with_receipts):
        with app_with_receipts.app_context():
            data = get_receipt_dashboard()
            assert data["total_this_month"] == 0
            assert data["needs_review"] == 0
            assert data["approved_total"] == Decimal("0")

    def test_get_dashboard_with_data(self, app_with_receipts, sample_receipt):
        with app_with_receipts.app_context():
            data = get_receipt_dashboard()
            assert data["total_this_month"] >= 1

    def test_approve_receipt_creates_expenses(self, app_with_receipts, sample_receipt, admin_user):
        with app_with_receipts.app_context():
            items = ReceiptLineItem.query.filter_by(receipt_id=sample_receipt).all()
            for item in items:
                set_line_allocation(item.id, AllocationType.GENERAL_EXPENSE)

            result = approve_receipt(sample_receipt, admin_user["id"])
            assert result["success"] is True

            receipt = db.session.get(Receipt, sample_receipt)
            assert receipt.status == ReceiptStatus.APPROVED

            expenses = Expense.query.filter_by(receipt_id=sample_receipt).all()
            assert len(expenses) > 0

    def test_reject_receipt(self, app_with_receipts, sample_receipt, admin_user):
        with app_with_receipts.app_context():
            result = reject_receipt(sample_receipt, admin_user["id"], "Test rejection")
            assert result["success"] is True
            receipt = db.session.get(Receipt, sample_receipt)
            assert receipt.status == ReceiptStatus.REJECTED

    def test_receipt_state_machine(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
            )
            db.session.add(receipt)
            db.session.commit()
            assert receipt.status == ReceiptStatus.UPLOADED

            receipt.status = ReceiptStatus.NEEDS_REVIEW
            db.session.commit()
            assert receipt.status == ReceiptStatus.NEEDS_REVIEW

            receipt.status = ReceiptStatus.APPROVED
            db.session.commit()
            assert receipt.status == ReceiptStatus.APPROVED


class TestAllocationEngine:
    def test_tax_allocation_proportional(self, app_with_receipts, sample_receipt):
        with app_with_receipts.app_context():
            result = allocate_taxes_and_fees(sample_receipt)
            assert result["success"] is True

            receipt = db.session.get(Receipt, sample_receipt)
            tax_total = receipt.tax_total or Decimal("0")

            items = ReceiptLineItem.query.filter_by(receipt_id=sample_receipt).all()
            allocated_tax = sum(i.line_tax or Decimal("0") for i in items)

            assert allocated_tax == tax_total

    def test_tax_allocation_math(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
                subtotal=Decimal("50.00"),
                tax_total=Decimal("5.00"),
                grand_total=Decimal("55.00"),
            )
            db.session.add(receipt)
            db.session.flush()

            item1 = ReceiptLineItem(
                receipt_id=receipt.id, row_order=0,
                description="Item 1", line_subtotal=Decimal("30.00"),
                line_total=Decimal("30.00"), taxable_status="taxable",
            )
            item2 = ReceiptLineItem(
                receipt_id=receipt.id, row_order=1,
                description="Item 2", line_subtotal=Decimal("20.00"),
                line_total=Decimal("20.00"), taxable_status="taxable",
            )
            db.session.add_all([item1, item2])
            db.session.commit()

            result = allocate_taxes_and_fees(receipt.id)
            assert result["success"] is True

            total_tax = item1.line_tax + item2.line_tax
            assert total_tax == Decimal("5.00")

    def test_penny_rounding(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
                subtotal=Decimal("100.00"),
                tax_total=Decimal("8.88"),
                grand_total=Decimal("108.88"),
            )
            db.session.add(receipt)
            db.session.flush()

            items = []
            for i in range(10):
                item = ReceiptLineItem(
                    receipt_id=receipt.id, row_order=i,
                    description=f"Item {i}", line_subtotal=Decimal("10.00"),
                    line_total=Decimal("10.00"), taxable_status="taxable",
                )
                db.session.add(item)
                items.append(item)
            db.session.commit()

            result = allocate_taxes_and_fees(receipt.id)
            assert result["success"] is True

            total_tax = sum(i.line_tax or Decimal("0") for i in items)
            assert total_tax == Decimal("8.88")

    def test_split_allocation_validation(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(user_id=admin_user["id"], status=ReceiptStatus.UPLOADED)
            db.session.add(receipt)
            db.session.flush()

            item = ReceiptLineItem(
                receipt_id=receipt.id, row_order=0,
                description="Split Item", line_total=Decimal("100.00"),
            )
            db.session.add(item)
            db.session.flush()

            set_line_allocation(item.id, AllocationType.MARKET, amount=Decimal("60.00"), percent=Decimal("60"))
            set_line_allocation(item.id, AllocationType.GENERAL_EXPENSE, amount=Decimal("40.00"), percent=Decimal("40"))

            allocations = ReceiptLineAllocation.query.filter_by(receipt_line_item_id=item.id).all()
            total = sum(a.amount or Decimal("0") for a in allocations)
            assert total == Decimal("100.00")


class TestDuplicateDetection:
    def test_no_duplicate(self, app_with_receipts, sample_receipt):
        with app_with_receipts.app_context():
            result = check_duplicates(sample_receipt)
            assert result["is_duplicate"] is False
            assert len(result["possible_duplicates"]) == 0

    def test_hash_duplicate(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            r1 = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.APPROVED,
                merchant_name="Store",
                file_hash="hash123",
                grand_total=Decimal("50.00"),
            )
            r2 = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
                merchant_name="Store",
                file_hash="hash123",
                grand_total=Decimal("50.00"),
            )
            db.session.add_all([r1, r2])
            db.session.commit()

            result = check_duplicates(r2.id)
            assert result["is_duplicate"] is True
            assert len(result["possible_duplicates"]) >= 1

    def test_resolve_duplicate_keep(self, app_with_receipts, admin_user):
        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.POSSIBLE_DUPLICATE,
                file_hash="dup123",
            )
            db.session.add(receipt)
            db.session.commit()

            result = resolve_duplicate(receipt.id, "keep")
            assert result["success"] is True
            receipt = db.session.get(Receipt, receipt.id)
            assert receipt.status == ReceiptStatus.NEEDS_REVIEW


class TestReconciliationSummary:
    def test_reconciliation_returns_keys(self, app_with_receipts, sample_receipt):
        with app_with_receipts.app_context():
            summary = get_reconciliation_summary(sample_receipt)
            assert "parsed_line_subtotal" in summary
            assert "receipt_total" in summary
            assert "difference" in summary


class TestAuthZ:
    def test_receipt_dashboard_requires_login(self, app_with_receipts):
        client = app_with_receipts.test_client()
        response = client.get("/expenses/receipts/", follow_redirects=False)
        assert response.status_code in (302, 401)

    def test_receipt_dashboard_loads_for_admin(self, client):
        response = client.get("/expenses/receipts/")
        assert response.status_code in (200, 302)

    def test_upload_page_loads(self, client):
        response = client.get("/expenses/receipts/upload")
        assert response.status_code in (200, 302)

    def test_inbox_loads(self, client):
        response = client.get("/expenses/receipts/inbox")
        assert response.status_code in (200, 302)

    def test_receipt_image_route_serves_relative_stored_file(
        self, app_with_receipts, admin_user, client
    ):
        receipt_dir = app_with_receipts.config["RECEIPT_STORAGE_PATH"]
        file_path = f"{receipt_dir}/review-test.jpg"
        with open(file_path, "wb") as handle:
            handle.write(b"fake-image-bytes")

        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.NEEDS_REVIEW,
                original_file_id="review-test.jpg",
            )
            db.session.add(receipt)
            db.session.commit()
            receipt_id = receipt.id

        response = client.get(f"/expenses/receipts/{receipt_id}/image")
        assert response.status_code == 200
        assert response.data == b"fake-image-bytes"

    def test_review_page_embeds_pdf_receipts(
        self, app_with_receipts, admin_user, client
    ):
        receipt_dir = app_with_receipts.config["RECEIPT_STORAGE_PATH"]
        file_path = f"{receipt_dir}/review-test.pdf"
        with open(file_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n%fake\n")

        with app_with_receipts.app_context():
            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.NEEDS_REVIEW,
                original_file_id="review-test.pdf",
            )
            db.session.add(receipt)
            db.session.commit()
            receipt_id = receipt.id

        response = client.get(f"/expenses/receipts/{receipt_id}/review")
        assert response.status_code == 200
        assert b'type="application/pdf"' in response.data
        assert f"/expenses/receipts/{receipt_id}/image".encode() in response.data


class TestProviderInterface:
    def test_ocr_provider_interface(self):
        from app.services.receipt_providers.base import BaseReceiptProvider, ProviderResult
        assert hasattr(BaseReceiptProvider, "process")
        pr = ProviderResult(success=True, data={"test": "value"})
        assert pr.success is True
        assert pr.data == {"test": "value"}

    def test_ai_provider_mock_mode(self):
        from app.services.receipt_providers.ai_provider import AIExtractionProvider
        provider = AIExtractionProvider()
        result = provider.process("/fake/path.jpg", raw_ocr_text="test receipt", mock_key="test")
        assert result.success is True
        assert result.data is not None
        assert result.data["merchant_name"] == "Mock Supermarket"

    def test_process_receipt_with_mock_ai_creates_review_draft(
        self, app_with_receipts, admin_user, monkeypatch
    ):
        from app.services import receipts as receipt_service
        from app.services.receipt_providers.base import ProviderResult

        class FakePreprocessor:
            def process(self, file_path, **kwargs):
                return ProviderResult(
                    success=True,
                    data={
                        "preview_path": file_path,
                        "pages": [file_path],
                    },
                )

        class FakeOCR:
            def process(self, file_path, **kwargs):
                return ProviderResult(
                    success=True,
                    raw_text="Mock OCR text",
                    raw_json='{"lines": [{"text": "Mock OCR text"}]}',
                    data={"lines": [{"text": "Mock OCR text"}]},
                    diagnostics={"provider": "mock_ocr"},
                )

        monkeypatch.setattr(receipt_service, "ImagePreprocessorProvider", FakePreprocessor)
        monkeypatch.setattr(receipt_service, "OCRProvider", FakeOCR)

        with app_with_receipts.app_context():
            app_with_receipts.config["AI_RECEIPT_PARSING_ENABLED"] = True
            app_with_receipts.config["RECEIPT_AI_PROVIDER"] = "mock"

            receipt = Receipt(
                user_id=admin_user["id"],
                status=ReceiptStatus.UPLOADED,
                original_file_id="/tmp/mock-receipt.jpg",
                subtotal=Decimal("1.23"),
            )
            db.session.add(receipt)
            db.session.commit()

            result = receipt_service.process_receipt(receipt.id)

            assert result["success"] is True
            receipt = db.session.get(Receipt, receipt.id)
            assert receipt.status == ReceiptStatus.NEEDS_REVIEW
            assert receipt.ai_extracted_json is not None
            assert receipt.merchant_name == "Mock Supermarket"
            assert receipt.subtotal == Decimal("42.50")
            assert receipt.grand_total == Decimal("46.40")
            assert receipt.parser_model == "test"
            assert receipt.confidence_overall == Decimal("0.9200")

            items = ReceiptLineItem.query.filter_by(receipt_id=receipt.id).all()
            assert len(items) == 3
            assert all(item.needs_review for item in items)
            assert Expense.query.filter_by(receipt_id=receipt.id).count() == 0


class TestBulkAssignment:
    def test_bulk_assign_all_items(self, app_with_receipts, sample_receipt):
        with app_with_receipts.app_context():
            items = ReceiptLineItem.query.filter_by(receipt_id=sample_receipt).all()
            item_ids = [i.id for i in items]

            count = bulk_assign_line_items(item_ids, AllocationType.MARKET)
            assert count == len(item_ids)

            allocations = ReceiptLineAllocation.query.all()
            assert len(allocations) == len(item_ids)
