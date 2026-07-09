from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ChannelPerformanceSummary,
    ImportSource,
    ProductSalesSummary,
    PromotedLegacyTable,
    SalesFactLine,
    SeasonalProductPerformance,
    utcnow,
)


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _int_cents(val: Any) -> int:
    if val is None:
        return 0
    try:
        return int((Decimal(str(val)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation):
        return 0


def _decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal("0")


async def _fetch_promoted_data(db: AsyncSession, table_name: str) -> list[dict] | None:
    stmt = select(PromotedLegacyTable).where(PromotedLegacyTable.table_name == table_name)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    return record.normalized_data if record else None


async def rebuild_legacy_warehouse(db: AsyncSession) -> dict[str, Any]:
    await db.execute(delete(SalesFactLine).where(SalesFactLine.source == ImportSource.LEGACY_MARIADB.value))
    await db.execute(delete(ProductSalesSummary))
    await db.execute(delete(SeasonalProductPerformance))
    await db.execute(delete(ChannelPerformanceSummary))

    products_raw = await _fetch_promoted_data(db, "product")
    bookings_raw = await _fetch_promoted_data(db, "booking")
    booking_products_raw = await _fetch_promoted_data(db, "booking_products")

    products: dict[str, dict] = {}
    if products_raw:
        for p in products_raw:
            pid = str(p.get("id", ""))
            if pid:
                products[pid] = p

    bookings: dict[str, dict] = {}
    if bookings_raw:
        for b in bookings_raw:
            bid = str(b.get("id", ""))
            if bid:
                bookings[bid] = b

    fact_count = 0
    if booking_products_raw:
        for bp in booking_products_raw:
            qty_sold = _decimal(bp.get("qtySold", 0))
            if qty_sold <= 0:
                continue

            product_fk = str(bp.get("product_fk", ""))
            booking_fk = str(bp.get("booking_fk", ""))

            product = products.get(product_fk, {})
            booking = bookings.get(booking_fk, {})

            sale_date = _parse_date(booking.get("info_datestart")) or _parse_date(booking.get("info_dateend"))
            unit_price = _decimal(bp.get("price", 0))
            net_cents = _int_cents(unit_price * qty_sold)
            gross_cents = _int_cents(unit_price * qty_sold)
            discount_cents = _int_cents(bp.get("discount", 0))

            product_name = str(product.get("name", bp.get("name", "Unknown Product")))
            product_key = str(product.get("sku", product_fk)) or product_name.casefold().replace(" ", "_")
            category = str(product.get("category", "")) or None

            channel_name = f"Legacy Market: {str(booking.get('id', booking_fk))[:12]}"

            fact = SalesFactLine(
                source=ImportSource.LEGACY_MARIADB.value,
                source_row_id=str(bp.get("id", "")),
                sale_date=sale_date,
                sale_year=sale_date.year if sale_date else None,
                sale_month=sale_date.month if sale_date else None,
                product_key=product_key,
                product_name=product_name,
                category_name=category,
                channel_name=channel_name,
                quantity=qty_sold,
                gross_sales_cents=gross_cents,
                discount_cents=discount_cents,
                net_sales_cents=net_cents,
                tax_cents=0,
                evidence={
                    "source": "legacy_mariadb",
                    "booking_products_row": {
                        "id": bp.get("id"),
                        "booking_fk": booking_fk,
                        "product_fk": product_fk,
                        "price": str(unit_price),
                        "qty": str(bp.get("qty", "")),
                        "qtySold": str(qty_sold),
                    },
                    "product": {"name": product_name, "sku": product.get("sku"), "category": category},
                    "booking": {"id": booking.get("id"), "date": str(sale_date) if sale_date else None},
                },
            )
            db.add(fact)
            fact_count += 1

    # Flush facts so aggregations see them
    await db.flush()

    # Aggregate into summaries
    facts = (await db.execute(select(SalesFactLine).where(SalesFactLine.source == ImportSource.LEGACY_MARIADB.value))).scalars().all()

    product_groups: dict[str, list[SalesFactLine]] = defaultdict(list)
    seasonal_groups: dict[tuple[str, int], list[SalesFactLine]] = defaultdict(list)
    channel_groups: dict[str, list[SalesFactLine]] = defaultdict(list)

    for fact in facts:
        product_groups[fact.product_key].append(fact)
        if fact.sale_month is not None:
            seasonal_groups[(fact.product_key, fact.sale_month)].append(fact)
        channel_groups[fact.channel_name].append(fact)

    for product_key, rows in product_groups.items():
        total_units = sum(Decimal(row.quantity) for row in rows)
        total_net = sum(row.net_sales_cents for row in rows)
        transactions = {row.transaction_id for row in rows if row.transaction_id}
        active_months = {(row.sale_year, row.sale_month) for row in rows if row.sale_year and row.sale_month}
        dated = [row.sale_date for row in rows if row.sale_date]
        avg_units = total_units / Decimal(max(len(active_months), 1)) if active_months else Decimal("0")
        avg_cents = int((Decimal(total_net) / total_units).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total_units else 0
        db.add(
            ProductSalesSummary(
                product_key=product_key,
                product_name=rows[0].product_name,
                category_name=rows[0].category_name,
                total_units=total_units,
                total_net_sales_cents=total_net,
                transaction_count=len(transactions),
                active_months=len(active_months),
                avg_units_per_active_month=avg_units,
                avg_net_sales_cents_per_unit=avg_cents,
                first_sale_date=min(dated) if dated else None,
                last_sale_date=max(dated) if dated else None,
                updated_at=utcnow(),
            )
        )

    for (product_key, sale_month), rows in seasonal_groups.items():
        transactions = {row.transaction_id for row in rows if row.transaction_id}
        db.add(
            SeasonalProductPerformance(
                product_key=product_key,
                product_name=rows[0].product_name,
                sale_month=sale_month,
                total_units=sum(Decimal(row.quantity) for row in rows),
                total_net_sales_cents=sum(row.net_sales_cents for row in rows),
                transaction_count=len(transactions),
                updated_at=utcnow(),
            )
        )

    for channel_name, rows in channel_groups.items():
        transactions = {row.transaction_id for row in rows if row.transaction_id}
        active_months = {(row.sale_year, row.sale_month) for row in rows if row.sale_year and row.sale_month}
        db.add(
            ChannelPerformanceSummary(
                channel_name=channel_name,
                total_units=sum(Decimal(row.quantity) for row in rows),
                total_net_sales_cents=sum(row.net_sales_cents for row in rows),
                transaction_count=len(transactions),
                active_months=len(active_months),
                updated_at=utcnow(),
            )
        )

    await db.commit()

    return {
        "source": ImportSource.LEGACY_MARIADB.value,
        "facts_created": fact_count,
        "product_summaries": len(product_groups),
        "seasonal_summaries": len(seasonal_groups),
        "channel_summaries": len(channel_groups),
    }
