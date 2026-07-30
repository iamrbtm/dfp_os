from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AliasEntityType,
    ChannelPerformanceSummary,
    HistoricalAliasMapping,
    ImportSource,
    ImportStatus,
    ProductSalesSummary,
    SalesFactLine,
    SeasonalProductPerformance,
    SquareItemRaw,
    WarehouseBuild,
    utcnow,
)


@dataclass
class ProductAlias:
    product_key: str
    product_name: str


def _normalize_key(value: str | None) -> str:
    normalized = " ".join((value or "").strip().casefold().split())
    return normalized or "unknown"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_decimal(value: str | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _int_cents(value: int | None) -> int:
    return int(value or 0)


async def _reviewed_product_aliases(db: AsyncSession) -> dict[str, ProductAlias]:
    result = await db.execute(
        select(HistoricalAliasMapping).where(
            HistoricalAliasMapping.source == ImportSource.SQUARE_CSV.value,
            HistoricalAliasMapping.entity_type.in_([AliasEntityType.PRODUCT.value, AliasEntityType.VARIANT.value]),
            HistoricalAliasMapping.reviewed.is_(True),
            HistoricalAliasMapping.target_entity_id.is_not(None),
        )
    )
    aliases: dict[str, ProductAlias] = {}
    for mapping in result.scalars().all():
        aliases[_normalize_key(mapping.source_value)] = ProductAlias(
            product_key=str(mapping.target_entity_id),
            product_name=mapping.target_display_name or mapping.source_value,
        )
    return aliases


def _resolve_product(row: SquareItemRaw, aliases: dict[str, ProductAlias]) -> ProductAlias:
    source_name = row.item or row.sku or "Unknown Product"
    alias = aliases.get(_normalize_key(source_name))
    if alias is not None:
        return alias
    return ProductAlias(product_key=_normalize_key(f"{row.sku or ''}|{source_name}"), product_name=source_name)


async def rebuild_square_sales_warehouse(db: AsyncSession) -> WarehouseBuild:
    build = WarehouseBuild(
        source=ImportSource.SQUARE_CSV.value,
        status=ImportStatus.RUNNING.value,
        started_at=utcnow(),
        build_metadata={"strategy": "rebuild_from_square_item_raw"},
    )
    db.add(build)
    await db.flush()

    try:
        await db.execute(delete(SalesFactLine).where(SalesFactLine.source == ImportSource.SQUARE_CSV.value))
        await db.execute(delete(ProductSalesSummary))
        await db.execute(delete(SeasonalProductPerformance))
        await db.execute(delete(ChannelPerformanceSummary))

        aliases = await _reviewed_product_aliases(db)
        raw_rows = (
            await db.execute(select(SquareItemRaw).order_by(SquareItemRaw.date, SquareItemRaw.row_number))
        ).scalars().all()

        fact_count = 0
        for row in raw_rows:
            product = _resolve_product(row, aliases)
            sale_date = _parse_date(row.date)
            qty = _parse_decimal(row.qty)
            fact = SalesFactLine(
                source=ImportSource.SQUARE_CSV.value,
                source_row_id=row.id,
                sale_date=sale_date,
                sale_year=sale_date.year if sale_date else None,
                sale_month=sale_date.month if sale_date else None,
                product_key=product.product_key,
                product_name=product.product_name,
                variant_key=_normalize_key(row.price_point_name) if row.price_point_name else None,
                category_name=row.category or None,
                channel_name=row.channel or row.location or "Unknown",
                sku=row.sku or None,
                transaction_id=row.transaction_id or None,
                quantity=qty,
                gross_sales_cents=_int_cents(row.gross_sales_cents),
                discount_cents=_int_cents(row.discounts_cents),
                net_sales_cents=_int_cents(row.net_sales_cents),
                tax_cents=_int_cents(row.tax_cents),
                evidence={
                    "square_row_id": row.id,
                    "source_row_hash": row.source_row_hash,
                    "transaction_id": row.transaction_id,
                    "raw_item": row.item,
                    "raw_category": row.category,
                    "raw_channel": row.channel,
                },
            )
            db.add(fact)
            fact_count += 1
        await db.flush()

        facts = (await db.execute(select(SalesFactLine))).scalars().all()
        product_groups: dict[str, list[SalesFactLine]] = defaultdict(list)
        seasonal_groups: dict[tuple[str, int], list[SalesFactLine]] = defaultdict(list)
        channel_groups: dict[str, list[SalesFactLine]] = defaultdict(list)
        for fact in facts:
            product_groups[fact.product_key].append(fact)
            if fact.sale_month is not None:
                seasonal_groups[(fact.product_key, fact.sale_month)].append(fact)
            channel_groups[fact.channel_name or "Unknown"].append(fact)

        for product_key, rows in product_groups.items():
            total_units = sum(Decimal(row.quantity) for row in rows)
            total_net = sum(row.net_sales_cents for row in rows)
            transactions = {row.transaction_id for row in rows if row.transaction_id}
            active_months = {(row.sale_year, row.sale_month) for row in rows if row.sale_year and row.sale_month}
            dated = [row.sale_date for row in rows if row.sale_date]
            avg_units = total_units / Decimal(max(len(active_months), 1))
            avg_cents = (
                int((Decimal(total_net) / total_units).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                if total_units
                else 0
            )
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

        build.status = ImportStatus.COMPLETED.value
        build.completed_at = utcnow()
        build.fact_rows = fact_count
        build.product_summary_rows = len(product_groups)
        build.seasonal_summary_rows = len(seasonal_groups)
        build.channel_summary_rows = len(channel_groups)
        await db.commit()
        await db.refresh(build)
        return build
    except Exception as exc:
        build.status = ImportStatus.FAILED.value
        build.error_message = str(exc)
        build.completed_at = utcnow()
        await db.commit()
        raise


async def list_product_summaries(db: AsyncSession, limit: int = 25) -> list[ProductSalesSummary]:
    result = await db.execute(
        select(ProductSalesSummary)
        .order_by(ProductSalesSummary.total_units.desc(), ProductSalesSummary.total_net_sales_cents.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_channel_summaries(db: AsyncSession, limit: int = 25) -> list[ChannelPerformanceSummary]:
    result = await db.execute(
        select(ChannelPerformanceSummary)
        .order_by(ChannelPerformanceSummary.total_net_sales_cents.desc(), ChannelPerformanceSummary.total_units.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_seasonal_summaries(
    db: AsyncSession, sale_month: int | None = None, limit: int = 25
) -> list[SeasonalProductPerformance]:
    stmt = select(SeasonalProductPerformance)
    if sale_month is not None:
        stmt = stmt.where(SeasonalProductPerformance.sale_month == sale_month)
    stmt = stmt.order_by(
        SeasonalProductPerformance.total_units.desc(),
        SeasonalProductPerformance.total_net_sales_cents.desc(),
    ).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
