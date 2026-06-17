from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Receipt, ReceiptLineItem, ReceiptLineAllocation, ReceiptStatus, Expense
from app.models.base import utc_now
from app.services.receipt_providers import ImagePreprocessorProvider, OCRProvider, AIExtractionProvider


def _compute_file_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _get_upload_folder() -> str:
    folder = current_app.config.get("RECEIPT_STORAGE_PATH") or os.path.join(
        current_app.config.get("UPLOAD_FOLDER", "uploads"), "receipts"
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_file(filename: str) -> bool:
    allowed = current_app.config.get("RECEIPT_ALLOWED_TYPES", "image/jpeg,image/png,image/heic,image/heif,application/pdf")
    ext = Path(filename).suffix.lower().lstrip(".")
    ext_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "heic": "image/heic", "heif": "image/heif", "pdf": "application/pdf",
    }
    return ext_map.get(ext, "") in allowed


def _max_upload_mb() -> int:
    return int(current_app.config.get("RECEIPT_MAX_UPLOAD_MB", 25))


def upload_receipt(file_obj, user_id: int, source_type: str = "upload") -> Receipt | None:
    if not file_obj or not file_obj.filename:
        return None

    if not _allowed_file(file_obj.filename):
        raise ValueError(f"File type not allowed: {file_obj.filename}")

    file_size = 0
    file_obj.seek(0, os.SEEK_END)
    file_size = file_obj.tell()
    file_obj.seek(0)

    if file_size > _max_upload_mb() * 1024 * 1024:
        raise ValueError(f"File exceeds maximum size of {_max_upload_mb()}MB")

    upload_folder = _get_upload_folder()
    filename = secure_filename(file_obj.filename)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique_name = f"{timestamp}_{filename}"
    file_path = os.path.join(upload_folder, unique_name)
    file_obj.save(file_path)

    file_hash = _compute_file_hash(file_path)

    duplicate = _check_duplicate_by_hash(file_hash)
    status = ReceiptStatus.POSSIBLE_DUPLICATE if duplicate else ReceiptStatus.UPLOADED

    receipt = Receipt(
        user_id=user_id,
        status=status,
        original_file_id=file_path,
        file_hash=file_hash,
        source_type=source_type,
        duplicate_group_id=duplicate.id if duplicate else None,
    )
    db.session.add(receipt)
    db.session.commit()
    return receipt


def process_receipt(receipt_id: int) -> dict[str, Any]:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"success": False, "errors": ["Receipt not found."]}

    if not receipt.original_file_id:
        return {"success": False, "errors": ["No uploaded file to process."]}

    results = {"preprocessing": None, "ocr": None, "ai": None}

    # Step 1: Preprocess image
    receipt.status = ReceiptStatus.PREPROCESSING
    db.session.commit()

    preprocessor = ImagePreprocessorProvider()
    preprocess_result = preprocessor.process(
        receipt.original_file_id,
        output_dir=str(Path(receipt.original_file_id).parent),
    )
    results["preprocessing"] = preprocess_result

    if not preprocess_result.success:
        receipt.status = ReceiptStatus.PROCESSING_FAILED
        db.session.commit()
        return {"success": False, "errors": preprocess_result.errors, "results": results}

    if preprocess_result.data:
        receipt.preview_file_id = preprocess_result.data.get("preview_path")
        receipt.thumbnail_file_id = preprocess_result.data.get("thumbnail_path")

    # Step 2: OCR
    receipt.status = ReceiptStatus.OCR_PROCESSING
    db.session.commit()

    ocr_provider = OCRProvider()
    ocr_config = current_app.config
    ocr_image = preprocess_result.data.get("enhanced_path") or preprocess_result.data.get("pages", [receipt.original_file_id])[0]
    ocr_result = ocr_provider.process(
        ocr_image,
        provider=ocr_config.get("RECEIPT_OCR_PROVIDER", "paddleocr"),
        enhanced_path=preprocess_result.data.get("enhanced_path"),
    )
    results["ocr"] = ocr_result

    if not ocr_result.success:
        receipt.status = ReceiptStatus.PROCESSING_FAILED
        receipt.raw_ocr_text = ocr_result.raw_text
        db.session.commit()
        return {"success": False, "errors": ocr_result.errors, "results": results}

    receipt.raw_ocr_text = ocr_result.raw_text
    receipt.raw_ocr_json = ocr_result.raw_json
    receipt.parser_provider = ocr_result.diagnostics.get("provider", "unknown")
    receipt.parser_version = ocr_result.diagnostics.get("provider", "unknown")

    # Step 3: AI extraction
    receipt.status = ReceiptStatus.AI_EXTRACTING
    db.session.commit()

    ai_provider = AIExtractionProvider()
    ai_result = ai_provider.process(
        receipt.original_file_id,
        raw_ocr_text=ocr_result.raw_text or "",
        ollama_base_url=ocr_config.get("OLLAMA_BASE_URL", "http://breath.local:11434"),
        ollama_fallback_url=ocr_config.get("OLLAMA_FALLBACK_URL", "http://localhost:11434"),
        model=ocr_config.get("OLLAMA_RECEIPT_MODEL", "qwen2.5vl:7b"),
    )
    results["ai"] = ai_result

    if ai_result.success and ai_result.data:
        receipt.ai_extracted_json = ai_result.raw_json
        receipt.parser_model = ai_result.diagnostics.get("model", "unknown")
        _apply_ai_extraction(receipt, ai_result.data)
        receipt.status = ReceiptStatus.NEEDS_REVIEW
    else:
        receipt.status = ReceiptStatus.NEEDS_REVIEW

    receipt.confidence_overall = Decimal(str(ai_result.confidence)) if ai_result.confidence is not None else None

    db.session.commit()
    return {"success": True, "results": results}


def _apply_ai_extraction(receipt: Receipt, data: dict):
    receipt.merchant_name = data.get("merchant_name") or receipt.merchant_name
    receipt.store_name = data.get("store_name") or receipt.store_name
    receipt.store_number = data.get("store_number") or receipt.store_number
    receipt.address_line_1 = data.get("address_line_1") or receipt.address_line_1
    receipt.address_line_2 = data.get("address_line_2") or receipt.address_line_2
    receipt.city = data.get("city") or receipt.city
    receipt.state = data.get("state") or receipt.state
    receipt.postal_code = data.get("postal_code") or receipt.postal_code
    receipt.phone = data.get("phone") or receipt.phone
    receipt.receipt_number = data.get("receipt_number") or receipt.receipt_number
    receipt.transaction_number = data.get("transaction_number") or receipt.transaction_number

    if data.get("date_time"):
        try:
            receipt.date_time = datetime.fromisoformat(data["date_time"])
        except (ValueError, TypeError):
            pass

    receipt.timezone = data.get("timezone") or receipt.timezone
    receipt.subtotal = _safe_decimal(data.get("subtotal"))
    receipt.tax_total = _safe_decimal(data.get("tax_total"))
    receipt.fee_total = _safe_decimal(data.get("fee_total"))
    receipt.discount_total = _safe_decimal(data.get("discount_total"))
    receipt.tip_total = _safe_decimal(data.get("tip_total"))
    receipt.deposit_total = _safe_decimal(data.get("deposit_total"))
    receipt.rounding_adjustment = _safe_decimal(data.get("rounding_adjustment"))
    receipt.grand_total = _safe_decimal(data.get("grand_total"))
    receipt.payment_method = data.get("payment_method") or receipt.payment_method
    receipt.payment_card_brand = data.get("payment_card_brand") or receipt.payment_card_brand
    receipt.payment_card_last4 = data.get("payment_card_last4") or receipt.payment_card_last4
    receipt.currency = data.get("currency") or receipt.currency

    low_conf = data.get("low_confidence_fields", [])
    receipt.low_confidence_flags = json.dumps(low_conf) if low_conf else None

    line_items_data = data.get("line_items", [])
    for i, item_data in enumerate(line_items_data):
        line_item = ReceiptLineItem(
            receipt_id=receipt.id,
            row_order=i,
            description=item_data.get("description"),
            sku=item_data.get("sku"),
            upc=item_data.get("upc"),
            quantity=_safe_decimal(item_data.get("quantity")),
            unit_price=_safe_decimal(item_data.get("unit_price")),
            line_total=_safe_decimal(item_data.get("line_total")),
            line_discount=_safe_decimal(item_data.get("line_discount")),
            line_tax=_safe_decimal(item_data.get("line_tax")),
            taxable_status="taxable" if item_data.get("taxable") else "unknown",
            confidence_description=Decimal(str(item_data.get("confidence", 0.5))) if item_data.get("confidence") else None,
            needs_review=True,
        )
        db.session.add(line_item)


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _check_duplicate_by_hash(file_hash: str) -> Receipt | None:
    return Receipt.query.filter(
        Receipt.file_hash == file_hash,
        Receipt.deleted_at.is_(None),
    ).first()


def approve_receipt(receipt_id: int, approved_by_id: int) -> dict[str, Any]:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"success": False, "errors": ["Receipt not found."]}

    if receipt.status == ReceiptStatus.APPROVED:
        return {"success": False, "errors": ["Receipt already approved."]}

    receipt.status = ReceiptStatus.APPROVED
    receipt.approved_at = utc_now()
    receipt.approved_by_id = approved_by_id
    db.session.commit()

    _create_expense_records(receipt)

    return {"success": True}


def _create_expense_records(receipt: Receipt):
    from app.models import ExpenseCategory

    line_items = ReceiptLineItem.query.filter_by(receipt_id=receipt.id).all()
    for item in line_items:
        if item.is_personal_or_excluded:
            continue

        allocations = ReceiptLineAllocation.query.filter_by(receipt_line_item_id=item.id).all()
        if allocations:
            for alloc in allocations:
                expense = Expense(
                    date=receipt.date_time.date() if receipt.date_time else utc_now().date(),
                    vendor=receipt.merchant_name or "Unknown Vendor",
                    category=_map_allocation_to_category(alloc.allocation_type),
                    description=item.description or "Receipt line item",
                    amount=alloc.amount or item.line_total or Decimal("0"),
                    payment_method=receipt.payment_method,
                    receipt_id=receipt.id,
                    receipt_file_path=receipt.original_file_id,
                    tax_deductible=True,
                    notes=f"From receipt #{receipt.id} line item #{item.id} allocation #{alloc.id}",
                )
                if alloc.allocation_type == "market":
                    expense.related_market_id = alloc.market_id
                elif alloc.allocation_type == "custom_job":
                    expense.related_order_id = alloc.custom_job_id
                db.session.add(expense)
        else:
            expense = Expense(
                date=receipt.date_time.date() if receipt.date_time else utc_now().date(),
                vendor=receipt.merchant_name or "Unknown Vendor",
                category=ExpenseCategory.OTHER,
                description=item.description or "Receipt line item (unallocated)",
                amount=item.line_total or Decimal("0"),
                payment_method=receipt.payment_method,
                receipt_id=receipt.id,
                receipt_file_path=receipt.original_file_id,
                tax_deductible=True,
                notes=f"From receipt #{receipt.id} line item #{item.id} (unallocated)",
            )
            db.session.add(expense)

    db.session.commit()


def _map_allocation_to_category(allocation_type: str):
    from app.models import ExpenseCategory
    mapping = {
        "market": ExpenseCategory.BOOTH_FEES,
        "custom_job": ExpenseCategory.OTHER,
        "inventory": ExpenseCategory.FILAMENT,
        "general_expense": ExpenseCategory.OTHER,
        "personal_excluded": ExpenseCategory.OTHER,
    }
    return mapping.get(allocation_type, ExpenseCategory.OTHER)


def reject_receipt(receipt_id: int, rejected_by_id: int, reason: str = "") -> dict[str, Any]:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"success": False, "errors": ["Receipt not found."]}

    receipt.status = ReceiptStatus.REJECTED
    receipt.rejected_at = utc_now()
    receipt.rejected_by_id = rejected_by_id
    if reason:
        receipt.notes = (receipt.notes or "") + f"\nRejected: {reason}"
    db.session.commit()
    return {"success": True}


def get_receipt_dashboard() -> dict[str, Any]:
    from app.models import ReceiptLineItem
    from sqlalchemy import func

    now = utc_now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_this_month = Receipt.query.filter(
        Receipt.created_at >= month_start,
        Receipt.deleted_at.is_(None),
    ).count()

    needs_review = Receipt.query.filter(
        Receipt.status == ReceiptStatus.NEEDS_REVIEW,
        Receipt.deleted_at.is_(None),
    ).count()

    possible_duplicates = Receipt.query.filter(
        Receipt.status == ReceiptStatus.POSSIBLE_DUPLICATE,
        Receipt.deleted_at.is_(None),
    ).count()

    approved_total = (
        db.session.query(func.sum(Receipt.grand_total))
        .filter(
            Receipt.status == ReceiptStatus.APPROVED,
            Receipt.deleted_at.is_(None),
        )
        .scalar() or Decimal("0")
    )

    unallocated = (
        db.session.query(func.count(ReceiptLineItem.id))
        .join(Receipt, ReceiptLineItem.receipt_id == Receipt.id)
        .filter(
            ~ReceiptLineItem.allocations.any(),
            Receipt.deleted_at.is_(None),
        )
        .scalar() or 0
    )

    recent = (
        Receipt.query.filter(Receipt.deleted_at.is_(None))
        .order_by(Receipt.created_at.desc())
        .limit(10)
        .all()
    )

    vendors = (
        db.session.query(
            Receipt.merchant_name,
            func.count(Receipt.id).label("count"),
            func.sum(Receipt.grand_total).label("total"),
        )
        .filter(
            Receipt.merchant_name.isnot(None),
            Receipt.deleted_at.is_(None),
        )
        .group_by(Receipt.merchant_name)
        .order_by(func.sum(Receipt.grand_total).desc())
        .limit(10)
        .all()
    )

    return {
        "total_this_month": total_this_month,
        "needs_review": needs_review,
        "possible_duplicates": possible_duplicates,
        "approved_total": approved_total,
        "unallocated": unallocated,
        "recent": recent,
        "vendors": [
            {"name": r[0], "count": r[1], "total": r[2]} for r in vendors
        ],
    }
