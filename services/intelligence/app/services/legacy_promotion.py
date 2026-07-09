from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LegacyImportRowStage,
    LegacyTableManifest,
    LegacyTableReviewState,
    PromotedLegacyTable,
    TableReviewDecision,
    utcnow,
)


def _detect_entity_type(table_name: str) -> str:
    lower = table_name.lower()
    if lower in ("product", "products", "item", "items"):
        return "product"
    if lower in ("customer", "customers"):
        return "customer"
    if lower in ("order", "orders"):
        return "order"
    if lower in ("order_item", "order_items", "orderitem", "orderitems"):
        return "order_item"
    if "inventory" in lower or lower in ("stock", "stock_item"):
        return "inventory"
    if lower in ("category", "categories"):
        return "category"
    if lower in ("vendor", "vendors", "supplier", "suppliers"):
        return "vendor"
    if lower in ("payment", "payments"):
        return "payment"
    if "print" in lower or "printer" in lower:
        return "print_job"
    if "filament" in lower or "spool" in lower:
        return "filament"
    if lower in ("market", "markets", "event", "events"):
        return "market"
    if lower in ("receipt", "receipts"):
        return "receipt"
    if "shipping" in lower:
        return "shipping"
    if "user" in lower or "staff" in lower or "employee" in lower:
        return "user"
    return "other"


def _detect_primary_key_columns(rows: list[dict]) -> list[str]:
    candidates = ("id", "ID", "Id", "uid", "UID", "uuid", "UUID")
    if not rows:
        return []
    for col in rows[0]:
        if col in candidates:
            return [col]
    return []


async def promote_kept_tables(db: AsyncSession) -> dict[str, object]:
    reviews = await db.execute(
        select(LegacyTableReviewState).where(
            LegacyTableReviewState.decision == TableReviewDecision.KEEP.value,
        )
    )
    reviews = reviews.scalars().all()

    if not reviews:
        return {"promoted": 0, "skipped": 0, "tables": []}

    results: list[dict] = []
    promoted_count = 0
    skipped_count = 0

    for review in reviews:
        existing = await db.execute(
            select(PromotedLegacyTable).where(
                and_(
                    PromotedLegacyTable.import_batch_id.is_(None),
                    PromotedLegacyTable.table_name == review.table_name,
                )
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            results.append({"table_name": review.table_name, "status": "already_promoted"})
            continue

        manifest = await db.execute(
            select(LegacyTableManifest)
            .where(LegacyTableManifest.table_name == review.table_name)
            .order_by(LegacyTableManifest.created_at.desc())
        )
        manifest = manifest.scalar_one_or_none()
        if not manifest:
            skipped_count += 1
            results.append({"table_name": review.table_name, "status": "no_manifest"})
            continue

        rows = await db.execute(
            select(LegacyImportRowStage).where(
                and_(
                    LegacyImportRowStage.source_table_name == review.table_name,
                    LegacyImportRowStage.import_batch_id == manifest.import_batch_id,
                    LegacyImportRowStage.import_error.is_(None),
                )
            ).order_by(LegacyImportRowStage.row_number)
        )
        rows = rows.scalars().all()

        if not rows:
            skipped_count += 1
            results.append({"table_name": review.table_name, "status": "no_rows"})
            continue

        col_names = rows[0].column_names
        normalized_rows = []
        for r in rows:
            normalized_rows.append(r.raw_payload)

        entity_type = _detect_entity_type(review.table_name)

        promoted = PromotedLegacyTable(
            table_name=review.table_name,
            import_batch_id=manifest.import_batch_id,
            review_state_id=review.id,
            target_entity_type=entity_type,
            column_names=col_names,
            row_count=len(normalized_rows),
            normalized_data=normalized_rows,
            promoted_at=utcnow(),
        )
        db.add(promoted)
        promoted_count += 1
        results.append({
            "table_name": review.table_name,
            "status": "promoted",
            "entity_type": entity_type,
            "row_count": len(normalized_rows),
        })

    await db.commit()
    return {
        "promoted": promoted_count,
        "skipped": skipped_count,
        "tables": results,
    }


async def list_promoted_tables(db: AsyncSession) -> list[dict[str, object]]:
    ptables = await db.execute(
        select(PromotedLegacyTable).order_by(PromotedLegacyTable.table_name)
    )
    ptables = ptables.scalars().all()
    return [
        {
            "id": t.id,
            "table_name": t.table_name,
            "target_entity_type": t.target_entity_type,
            "row_count": t.row_count,
            "column_names": t.column_names,
            "promoted_at": t.promoted_at.isoformat() if t.promoted_at else None,
        }
        for t in ptables
    ]
