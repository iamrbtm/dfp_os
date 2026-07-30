from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NormalizedEntity,
    PipelineRun,
    PromotedLegacyTable,
    utcnow,
)

MapperFunc = Callable[[dict], dict[str, Any] | None]

_MAPPERS: dict[str, MapperFunc] = {}


def register_mapper(entity_type: str, func: MapperFunc) -> None:
    _MAPPERS[entity_type] = func


def _str(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


def _int_val(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(Decimal(str(val)))
    except (ValueError, TypeError):
        return None


def _cents(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(Decimal(str(val)) * 100)
    except (ValueError, TypeError):
        return None


def _date_val(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _map_product(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "product",
        "name": _str(row.get("name") or row.get("productName") or row.get("title")),
        "sku": _str(row.get("sku") or row.get("SKU") or row.get("skuCode")),
        "category": _str(row.get("category") or row.get("categoryName")),
        "description": _str(row.get("description") or row.get("desc")),
        "price_cents": _cents(row.get("price") or row.get("unitPrice") or row.get("cost")),
        "quantity": _int_val(row.get("quantity") or row.get("qty") or row.get("stock")),
        "status_value": _str(row.get("status") or row.get("isActive") or row.get("active")),
        "vendor_name": _str(row.get("vendor") or row.get("supplier")),
    }


def _map_customer(row: dict) -> dict[str, Any] | None:
    first = _str(row.get("firstname") or row.get("firstName") or row.get("first_name"))
    last = _str(row.get("lastname") or row.get("lastName") or row.get("last_name"))
    full = _str(row.get("name") or row.get("fullName") or row.get("display_name") or row.get("displayname"))
    if not full and (first or last):
        full = f"{first} {last}".strip()
    email = row.get("email") or row.get("emailAddress") or row.get("email_address") or ""
    return {
        "entity_type": "customer",
        "name": full,
        "sku": _str(email),
        "description": _str(row.get("notes") or row.get("note")),
        "original_primary_key": _str(row.get("id") or row.get("customerId") or row.get("userid")),
    }


def _map_order(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "order",
        "name": _str(row.get("orderNumber") or row.get("order_number") or row.get("name") or row.get("id")),
        "sku": _str(row.get("orderNumber") or row.get("order_number")),
        "amount_cents": _cents(
            row.get("total") or row.get("totalAmount") or row.get("amount") or row.get("grandTotal")
        ),
        "date_value": _date_val(
            row.get("date") or row.get("orderDate") or row.get("createdAt") or row.get("created_at")
        ),
        "status_value": _str(row.get("status") or row.get("orderStatus")),
        "customer_name": _str(row.get("customer") or row.get("customerName") or row.get("customer_name")),
        "original_primary_key": _str(row.get("id") or row.get("orderId")),
    }


def _map_order_item(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "order_item",
        "name": _str(row.get("name") or row.get("product_name") or row.get("itemName") or row.get("productName")),
        "sku": _str(row.get("sku") or row.get("productCode")),
        "quantity": _int_val(row.get("qty") or row.get("qtySold") or row.get("quantity")),
        "price_cents": _cents(row.get("price") or row.get("unitPrice")),
        "amount_cents": _cents(row.get("total") or row.get("lineTotal") or row.get("subtotal")),
        "date_value": _date_val(row.get("date") or row.get("orderDate")),
        "original_primary_key": _str(row.get("id") or row.get("lineId") or row.get("orderItemId")),
    }


def _map_inventory(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "inventory",
        "name": _str(row.get("name") or row.get("productName") or row.get("itemName")),
        "sku": _str(row.get("sku") or row.get("productCode")),
        "quantity": _int_val(row.get("qty") or row.get("quantity") or row.get("onHand") or row.get("stockLevel")),
        "price_cents": _cents(row.get("cost") or row.get("unitCost")),
        "category": _str(row.get("category") or row.get("location")),
        "status_value": _str(row.get("status")),
        "original_primary_key": _str(row.get("id")),
    }


def _map_filament(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "filament",
        "name": _str(row.get("name") or row.get("materialName") or row.get("type") or row.get("color")),
        "sku": _str(row.get("sku") or row.get("materialCode")),
        "category": _str(row.get("materialType") or row.get("type")),
        "quantity": _int_val(row.get("weight") or row.get("grams") or row.get("remaining")),
        "price_cents": _cents(row.get("cost") or row.get("price")),
        "vendor_name": _str(row.get("vendor") or row.get("supplier")),
        "description": _str(row.get("color") or row.get("colorName")),
        "original_primary_key": _str(row.get("id") or row.get("spoolId")),
    }


def _map_print_job(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "print_job",
        "name": _str(row.get("name") or row.get("jobName") or row.get("fileName") or row.get("file")),
        "sku": _str(row.get("sku") or row.get("productCode")),
        "status_value": _str(row.get("status") or row.get("jobStatus") or row.get("state")),
        "quantity": _int_val(row.get("copies") or row.get("qty") or row.get("count")),
        "date_value": _date_val(
            row.get("date") or row.get("startedAt") or row.get("started_at") or row.get("createdAt")
        ),
        "category": _str(row.get("printer") or row.get("printerName") or row.get("printer_id")),
        "description": _str(row.get("notes") or row.get("error") or row.get("failureReason")),
        "original_primary_key": _str(row.get("id") or row.get("jobId") or row.get("printJobId")),
    }


def _map_market(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "market",
        "name": _str(row.get("name") or row.get("marketName") or row.get("eventName") or row.get("title")),
        "date_value": _date_val(
            row.get("date") or row.get("eventDate") or row.get("startDate") or row.get("info_datestart")
        ),
        "status_value": _str(row.get("status") or row.get("eventStatus")),
        "vendor_name": _str(row.get("organizer") or row.get("host")),
        "amount_cents": _cents(row.get("fee") or row.get("boothFee") or row.get("registrationFee")),
        "original_primary_key": _str(row.get("id") or row.get("eventId")),
    }


def _map_category(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "category",
        "name": _str(row.get("name") or row.get("categoryName") or row.get("title")),
        "description": _str(row.get("description") or row.get("desc")),
        "original_primary_key": _str(row.get("id") or row.get("categoryId")),
    }


def _map_vendor(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "vendor",
        "name": _str(row.get("name") or row.get("vendorName") or row.get("company") or row.get("supplier")),
        "sku": _str(row.get("email") or row.get("emailAddress")),
        "description": _str(row.get("notes") or row.get("contactInfo") or row.get("phone")),
        "original_primary_key": _str(row.get("id") or row.get("vendorId")),
    }


def _map_payment(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "payment",
        "amount_cents": _cents(row.get("amount") or row.get("total") or row.get("paymentAmount")),
        "date_value": _date_val(row.get("date") or row.get("paymentDate") or row.get("createdAt")),
        "status_value": _str(row.get("status") or row.get("paymentStatus")),
        "customer_name": _str(row.get("customer") or row.get("customerName")),
        "original_primary_key": _str(row.get("id") or row.get("paymentId") or row.get("transactionId")),
    }


def _map_receipt(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "receipt",
        "name": _str(row.get("vendor") or row.get("storeName") or row.get("merchant")),
        "vendor_name": _str(row.get("vendor") or row.get("storeName") or row.get("merchant")),
        "amount_cents": _cents(row.get("total") or row.get("amount")),
        "date_value": _date_val(row.get("date") or row.get("purchaseDate") or row.get("receiptDate")),
        "status_value": _str(row.get("status") or row.get("reviewStatus")),
        "description": _str(row.get("notes") or row.get("category")),
        "original_primary_key": _str(row.get("id") or row.get("receiptId")),
    }


def _map_user(row: dict) -> dict[str, Any] | None:
    first = _str(row.get("firstname") or row.get("firstName") or row.get("first_name"))
    last = _str(row.get("lastname") or row.get("lastName") or row.get("last_name"))
    full = _str(row.get("name") or row.get("username") or row.get("displayName"))
    if not full and (first or last):
        full = f"{first} {last}".strip()
    return {
        "entity_type": "user",
        "name": full,
        "sku": _str(row.get("email") or row.get("emailAddress")),
        "status_value": _str(row.get("status") or row.get("isActive") or row.get("role")),
        "original_primary_key": _str(row.get("id") or row.get("userId")),
    }


def _map_shipping(row: dict) -> dict[str, Any] | None:
    return {
        "entity_type": "shipping",
        "name": _str(row.get("method") or row.get("carrier") or row.get("shippingMethod")),
        "amount_cents": _cents(row.get("cost") or row.get("price") or row.get("shippingCost")),
        "date_value": _date_val(row.get("date") or row.get("shipDate")),
        "status_value": _str(row.get("status") or row.get("trackingStatus")),
        "original_primary_key": _str(row.get("id") or row.get("shippingId")),
    }


def _map_other(row: dict) -> dict[str, Any] | None:
    name = _str(row.get("name") or row.get("title") or row.get("id"))
    return {
        "entity_type": "other",
        "name": name,
        "original_primary_key": _str(row.get("id")),
    }


register_mapper("product", _map_product)
register_mapper("customer", _map_customer)
register_mapper("order", _map_order)
register_mapper("order_item", _map_order_item)
register_mapper("inventory", _map_inventory)
register_mapper("filament", _map_filament)
register_mapper("print_job", _map_print_job)
register_mapper("market", _map_market)
register_mapper("category", _map_category)
register_mapper("vendor", _map_vendor)
register_mapper("payment", _map_payment)
register_mapper("receipt", _map_receipt)
register_mapper("user", _map_user)
register_mapper("shipping", _map_shipping)
register_mapper("other", _map_other)


def get_mapper(entity_type: str) -> MapperFunc | None:
    return _MAPPERS.get(entity_type, _MAPPERS.get("other"))


async def run_pipeline(db: AsyncSession) -> dict[str, Any]:
    run = PipelineRun(
        status="running",
        started_at=utcnow(),
    )
    db.add(run)
    await db.flush()

    promoted_tables = (
        await db.execute(select(PromotedLegacyTable).order_by(PromotedLegacyTable.table_name))
    ).scalars().all()

    results: dict[str, dict[str, int]] = {}
    total_created = 0

    try:
        for pt in promoted_tables:
            entity_type = pt.target_entity_type or "other"
            mapper = get_mapper(entity_type)
            if mapper is None:
                continue

            if entity_type not in results:
                results[entity_type] = {"created": 0, "errors": 0, "skipped": 0}

            for row in pt.normalized_data:
                mapped = mapper(row)
                if mapped is None:
                    results[entity_type]["skipped"] += 1
                    continue

                entity = NormalizedEntity(
                    pipeline_run_id=run.id,
                    promoted_table_id=pt.id,
                    entity_type=mapped.get("entity_type", entity_type),
                    original_table_name=pt.table_name,
                    original_primary_key=mapped.get("original_primary_key"),
                    name=mapped.get("name"),
                    sku=mapped.get("sku"),
                    category=mapped.get("category"),
                    description=mapped.get("description"),
                    price_cents=mapped.get("price_cents"),
                    quantity=mapped.get("quantity"),
                    amount_cents=mapped.get("amount_cents"),
                    date_value=mapped.get("date_value"),
                    customer_name=mapped.get("customer_name"),
                    vendor_name=mapped.get("vendor_name"),
                    status_value=mapped.get("status_value"),
                    source_json=row,
                )
                db.add(entity)
                results[entity_type]["created"] += 1
                total_created += 1

        run.status = "completed"
        run.completed_at = utcnow()
        run.entity_counts = results
        await db.commit()

    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = utcnow()
        await db.commit()

    return {
        "id": run.id,
        "status": run.status,
        "entities_created": total_created,
        "results": [
            {"entity_type": k, "created": v["created"], "errors": v["errors"], "skipped": v["skipped"]}
            for k, v in results.items()
        ],
    }


async def get_pipeline_status(db: AsyncSession) -> dict[str, Any]:
    latest = (
        await db.execute(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(1))
    ).scalar_one_or_none()

    if latest is None:
        return {
            "status": "idle",
            "last_run_at": None,
            "entities_created": 0,
            "results": [],
        }

    return {
        "id": latest.id,
        "status": latest.status,
        "last_run_at": latest.started_at.isoformat() if latest.started_at else None,
        "entities_created": (
            sum(v.get("created", 0) for v in (latest.entity_counts or {}).values())
        ),
        "results": [
            {"entity_type": k, "created": v.get("created", 0), "errors": v.get("errors", 0)}
            for k, v in (latest.entity_counts or {}).items()
        ],
    }
