from __future__ import annotations

import csv
import hashlib
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ImportBatch, ImportSource, ImportStatus, SquareItemRaw, utcnow
from app.schemas.imports import ImportBatchResponse, SquareImportResponse

REQUIRED_SQUARE_COLUMNS = {
    "Date",
    "Time",
    "Time Zone",
    "Category",
    "Item",
    "Qty",
    "Price Point Name",
    "SKU",
    "Gross Sales",
    "Discounts",
    "Net Sales",
    "Tax",
    "Transaction ID",
    "Payment ID",
    "Channel",
}
SENSITIVE_SQUARE_COLUMNS = {"Token", "PAN Suffix"}


def cents_from_square_money(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _row_hash(row: dict[str, str]) -> str:
    joined = "\x1f".join(f"{key}={row.get(key, '')}" for key in sorted(row))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sanitize_row(row: dict[str, str]) -> tuple[dict[str, str], bool]:
    sanitized = dict(row)
    sensitive_present = any(bool(sanitized.get(column)) for column in SENSITIVE_SQUARE_COLUMNS)
    for column in SENSITIVE_SQUARE_COLUMNS:
        sanitized.pop(column, None)
    return sanitized, sensitive_present


def _batch_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        source=batch.source,
        status=batch.status,
        source_name=batch.source_name,
        source_fingerprint=batch.source_fingerprint,
        row_count=batch.row_count,
        error_count=batch.error_count,
        error_message=batch.error_message,
    )


async def import_square_items_csv(db: AsyncSession, content: bytes, source_name: str | None = None) -> SquareImportResponse:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("Square CSV is empty or missing a header row.")
    missing = REQUIRED_SQUARE_COLUMNS.difference(reader.fieldnames)
    if missing:
        raise ValueError(f"Square CSV is missing required columns: {', '.join(sorted(missing))}.")

    batch = ImportBatch(
        source=ImportSource.SQUARE_CSV.value,
        status=ImportStatus.RUNNING.value,
        source_name=source_name,
        source_fingerprint=_fingerprint(content),
        started_at=utcnow(),
        import_metadata={
            "fieldnames": reader.fieldnames,
            "sensitive_columns_removed": sorted(SENSITIVE_SQUARE_COLUMNS.intersection(reader.fieldnames)),
        },
    )
    db.add(batch)
    await db.flush()

    imported = 0
    rejected = 0
    for row_number, row in enumerate(reader, start=2):
        sanitized, sensitive_present = _sanitize_row(row)
        if not any((value or "").strip() for value in sanitized.values()):
            rejected += 1
            continue
        db.add(
            SquareItemRaw(
                import_batch_id=batch.id,
                row_number=row_number,
                source_row_hash=_row_hash(sanitized),
                date=sanitized.get("Date") or None,
                time=sanitized.get("Time") or None,
                time_zone=sanitized.get("Time Zone") or None,
                category=sanitized.get("Category") or None,
                item=sanitized.get("Item") or None,
                qty=sanitized.get("Qty") or None,
                price_point_name=sanitized.get("Price Point Name") or None,
                sku=sanitized.get("SKU") or None,
                modifiers_applied=sanitized.get("Modifiers Applied") or None,
                gross_sales_cents=cents_from_square_money(sanitized.get("Gross Sales")),
                discounts_cents=cents_from_square_money(sanitized.get("Discounts")),
                net_sales_cents=cents_from_square_money(sanitized.get("Net Sales")),
                tax_cents=cents_from_square_money(sanitized.get("Tax")),
                transaction_id=sanitized.get("Transaction ID") or None,
                payment_id=sanitized.get("Payment ID") or None,
                device_name=sanitized.get("Device Name") or None,
                notes=sanitized.get("Notes") or None,
                details_url=sanitized.get("Details") or None,
                event_type=sanitized.get("Event Type") or None,
                location=sanitized.get("Location") or None,
                dining_option=sanitized.get("Dining Option") or None,
                customer_id=sanitized.get("Customer ID") or None,
                customer_name=sanitized.get("Customer Name") or None,
                customer_reference_id=sanitized.get("Customer Reference ID") or None,
                unit=sanitized.get("Unit") or None,
                count=sanitized.get("Count") or None,
                gtin=sanitized.get("GTIN") or None,
                itemization_type=sanitized.get("Itemization Type") or None,
                fulfillment_note=sanitized.get("Fulfillment Note") or None,
                channel=sanitized.get("Channel") or None,
                card_brand=sanitized.get("Card Brand") or None,
                sensitive_fields_present=sensitive_present,
                raw_payload=sanitized,
            )
        )
        imported += 1

    batch.status = ImportStatus.COMPLETED.value
    batch.completed_at = utcnow()
    batch.row_count = imported
    batch.error_count = rejected
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Square CSV import duplicated row numbers for this batch.") from None
    await db.refresh(batch)
    return SquareImportResponse(
        batch=_batch_response(batch),
        imported_rows=imported,
        rejected_rows=rejected,
        sensitive_fields_removed=sorted(SENSITIVE_SQUARE_COLUMNS.intersection(reader.fieldnames)),
    )
