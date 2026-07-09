from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    ImportBatch,
    ImportSource,
    ImportStatus,
    LegacyImportRowStage,
    LegacyMariaDbTableSnapshot,
    LegacyTableManifest,
    LegacyTableReviewState,
    TableReviewDecision,
    utcnow,
)
from app.schemas.imports import (
    ImportBatchResponse,
    LegacyImportAllRequest,
    LegacyImportAllResponse,
    LegacyJsonExportFile,
    LegacyJsonUploadResponse,
    LegacyMariaDbInspectRequest,
    LegacyMariaDbInspectResponse,
    LegacyMariaDbTableResponse,
    LegacyTableDeleteResponse,
    LegacyTableListResponse,
    LegacyTableManifestResponse,
    LegacyTableReviewRequest,
    LegacyTableReviewResponse,
    LegacyTableReviewStateResponse,
    LegacyTableWithReviewResponse,
)


@dataclass(frozen=True)
class LegacyMariaDbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int


def resolve_legacy_config(
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    user: str | None = None,
    password: str | None = None,
    connect_timeout: int | None = None,
) -> LegacyMariaDbConfig:
    host = host or settings.legacy_mariadb_host
    database = database or settings.legacy_mariadb_database
    user = user or settings.legacy_mariadb_user
    password = password or settings.legacy_mariadb_password
    port = port or settings.legacy_mariadb_port
    connect_timeout = connect_timeout or settings.legacy_mariadb_connect_timeout
    missing = [
        name
        for name, value in {
            "host": host,
            "database": database,
            "user": user,
            "password": password,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing legacy MariaDB connection settings: {', '.join(missing)}.")
    return LegacyMariaDbConfig(
        host=str(host),
        port=int(port),
        database=str(database),
        user=str(user),
        password=str(password),
        connect_timeout=int(connect_timeout),
    )


def _open_legacy_conn(config: LegacyMariaDbConfig):
    import pymysql

    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connect_timeout=config.connect_timeout,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _row_hash(row: dict[str, Any]) -> str:
    joined = "\x1f".join(f"{k}={json.dumps(row.get(k), default=str, sort_keys=True)}" for k in sorted(row))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch_legacy_schema(config: LegacyMariaDbConfig) -> list[dict[str, Any]]:
    conn = _open_legacy_conn(config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, table_rows
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                ORDER BY table_name
                """
            )
            tables = cur.fetchall()
            results: list[dict[str, Any]] = []
            for table in tables:
                table_name = table["TABLE_NAME"] if "TABLE_NAME" in table else table["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, column_key, column_default, extra
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE() AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table_name,),
                )
                columns = [
                    {
                        "name": row.get("COLUMN_NAME", row.get("column_name")),
                        "data_type": row.get("DATA_TYPE", row.get("data_type")),
                        "nullable": row.get("IS_NULLABLE", row.get("is_nullable")) == "YES",
                        "key": row.get("COLUMN_KEY", row.get("column_key")),
                        "default": row.get("COLUMN_DEFAULT", row.get("column_default")),
                        "extra": row.get("EXTRA", row.get("extra")),
                    }
                    for row in cur.fetchall()
                ]
                results.append(
                    {
                        "table_name": table_name,
                        "estimated_rows": table.get("TABLE_ROWS", table.get("table_rows")),
                        "columns": columns,
                        "primary_key_columns": [column["name"] for column in columns if column["key"] == "PRI"],
                    }
                )
        return results
    finally:
        conn.close()


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


def _manifest_response(manifest: LegacyTableManifest) -> LegacyTableManifestResponse:
    return LegacyTableManifestResponse(
        id=manifest.id,
        import_batch_id=manifest.import_batch_id,
        table_name=manifest.table_name,
        estimated_row_count=manifest.estimated_row_count,
        actual_row_count=manifest.actual_row_count,
        error_count=manifest.error_count,
        error_message=manifest.error_message,
        columns=manifest.columns,
        primary_key_columns=manifest.primary_key_columns,
        import_started_at=manifest.import_started_at,
        import_completed_at=manifest.import_completed_at,
        created_at=manifest.created_at,
    )


async def inspect_legacy_mariadb(
    db: AsyncSession,
    payload: LegacyMariaDbInspectRequest,
    schema_rows: list[dict[str, Any]] | None = None,
) -> LegacyMariaDbInspectResponse:
    config = resolve_legacy_config(
        host=payload.host,
        port=payload.port,
        database=payload.database,
        user=payload.user,
        password=payload.password,
        connect_timeout=payload.connect_timeout,
    )
    batch = ImportBatch(
        source=ImportSource.LEGACY_MARIADB.value,
        status=ImportStatus.RUNNING.value,
        source_name=config.database,
        started_at=utcnow(),
        import_metadata={"host": config.host, "port": config.port, "database": config.database},
    )
    db.add(batch)
    await db.flush()

    try:
        tables = schema_rows if schema_rows is not None else fetch_legacy_schema(config)
        responses: list[LegacyMariaDbTableResponse] = []
        for table in tables:
            snapshot = LegacyMariaDbTableSnapshot(
                import_batch_id=batch.id,
                table_name=table["table_name"],
                estimated_rows=table.get("estimated_rows"),
                columns=table["columns"],
                primary_key_columns=table.get("primary_key_columns"),
            )
            db.add(snapshot)
            responses.append(
                LegacyMariaDbTableResponse(
                    table_name=snapshot.table_name,
                    estimated_rows=snapshot.estimated_rows,
                    columns=snapshot.columns,
                    primary_key_columns=snapshot.primary_key_columns,
                )
            )
        batch.status = ImportStatus.COMPLETED.value
        batch.completed_at = utcnow()
        batch.row_count = len(responses)
        await db.commit()
        await db.refresh(batch)
        return LegacyMariaDbInspectResponse(batch=_batch_response(batch), tables=responses)
    except Exception as exc:
        batch.status = ImportStatus.FAILED.value
        batch.error_count = 1
        batch.error_message = str(exc)
        batch.completed_at = utcnow()
        await db.commit()
        raise


def _import_table_rows(
    config: LegacyMariaDbConfig,
    table_def: dict[str, Any],
    batch_id: str,
    manifest_id: str,
    batch_size: int = 500,
):
    table_name = table_def["table_name"]
    columns = table_def["columns"]
    pk_columns = table_def.get("primary_key_columns", [])
    col_names = [col["name"] for col in columns]

    conn = _open_legacy_conn(config)
    try:
        with conn.cursor() as cur:
            quoted_cols = ", ".join(f"`{col}`" for col in col_names)
            cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
            count_row = cur.fetchone()
            total = count_row.get("cnt", 0) if count_row else 0

            order_cols = ", ".join(f"`{c}`" for c in (pk_columns or [col_names[0]]))
            cur.execute(f"SELECT {quoted_cols} FROM `{table_name}` ORDER BY {order_cols}")

            row_number = 0
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    row_number += 1
                    try:
                        raw = {col: row.get(col) for col in col_names}
                        h = _row_hash(raw)
                        pk_value = _build_pk_value(raw, pk_columns)
                        yield {
                            "import_batch_id": batch_id,
                            "table_manifest_id": manifest_id,
                            "source_table_name": table_name,
                            "source_primary_key_value": pk_value,
                            "source_row_hash": h,
                            "row_number": row_number,
                            "column_names": col_names,
                            "raw_payload": raw,
                            "import_error": None,
                        }
                    except Exception as exc:
                        yield {
                            "import_batch_id": batch_id,
                            "table_manifest_id": manifest_id,
                            "source_table_name": table_name,
                            "source_primary_key_value": None,
                            "source_row_hash": "",
                            "row_number": row_number,
                            "column_names": col_names,
                            "raw_payload": {"_error": f"row processing failed: {exc}"},
                            "import_error": str(exc),
                        }
    finally:
        conn.close()


def _build_pk_value(row: dict[str, Any], pk_columns: list[str]) -> str | None:
    if not pk_columns:
        return None
    parts = []
    for col in pk_columns:
        val = row.get(col)
        parts.append(str(val) if val is not None else "NULL")
    return "|".join(parts)


async def import_all_legacy_tables(
    db: AsyncSession,
    payload: LegacyImportAllRequest,
    schema_rows: list[dict[str, Any]] | None = None,
) -> LegacyImportAllResponse:
    config = resolve_legacy_config(
        host=payload.host,
        port=payload.port,
        database=payload.database,
        user=payload.user,
        password=payload.password,
        connect_timeout=payload.connect_timeout,
    )

    batch = ImportBatch(
        source=ImportSource.LEGACY_MARIADB.value,
        status=ImportStatus.RUNNING.value,
        source_name=config.database,
        started_at=utcnow(),
        import_metadata={
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "batch_size": payload.batch_size,
        },
    )
    db.add(batch)
    await db.flush()

    try:
        tables = schema_rows if schema_rows is not None else fetch_legacy_schema(config)
        if payload.max_tables:
            tables = tables[: payload.max_tables]

        manifests: list[LegacyTableManifest] = []
        for table_def in tables:
            table_name = table_def["table_name"]
            manifest = LegacyTableManifest(
                import_batch_id=batch.id,
                table_name=table_name,
                estimated_row_count=table_def.get("estimated_rows"),
                columns=table_def["columns"],
                primary_key_columns=table_def.get("primary_key_columns"),
                import_started_at=utcnow(),
            )
            db.add(manifest)
            await db.flush()

            actual = 0
            errors = 0
            try:
                for row_data in _import_table_rows(
                    config=config,
                    table_def=table_def,
                    batch_id=batch.id,
                    manifest_id=manifest.id,
                    batch_size=payload.batch_size,
                ):
                    db.add(LegacyImportRowStage(**row_data))
                    if row_data["import_error"]:
                        errors += 1
                    else:
                        actual += 1

                    if (actual + errors) % payload.batch_size == 0:
                        await db.flush()

                manifest.actual_row_count = actual
                manifest.error_count = errors
                manifest.import_completed_at = utcnow()
            except Exception as exc:
                manifest.actual_row_count = actual
                manifest.error_count = errors + 1
                manifest.error_message = str(exc)
                manifest.import_completed_at = utcnow()

            manifests.append(manifest)

        total_rows = sum(m.actual_row_count for m in manifests)
        total_errors = sum(m.error_count for m in manifests)
        batch.status = ImportStatus.COMPLETED.value
        batch.completed_at = utcnow()
        batch.row_count = total_rows
        batch.error_count = total_errors
        await db.commit()
        await db.refresh(batch)
        return LegacyImportAllResponse(
            batch=_batch_response(batch),
            manifests=[_manifest_response(m) for m in manifests],
        )
    except Exception as exc:
        batch.status = ImportStatus.FAILED.value
        batch.error_count = 1
        batch.error_message = str(exc)
        batch.completed_at = utcnow()
        await db.commit()
        raise


async def list_imported_tables(db: AsyncSession) -> LegacyTableListResponse:
    manifest_subq = (
        select(
            LegacyTableManifest.import_batch_id,
            LegacyTableManifest.table_name,
            func.max(LegacyTableManifest.created_at).label("max_created"),
        )
        .group_by(LegacyTableManifest.import_batch_id, LegacyTableManifest.table_name)
        .subquery()
    )

    latest = (
        select(LegacyTableManifest)
        .join(
            manifest_subq,
            and_(
                LegacyTableManifest.import_batch_id == manifest_subq.c.import_batch_id,
                LegacyTableManifest.table_name == manifest_subq.c.table_name,
                LegacyTableManifest.created_at == manifest_subq.c.max_created,
            ),
        )
        .subquery()
    )

    count_subq = (
        select(func.count(LegacyImportRowStage.id))
        .where(
            LegacyImportRowStage.source_table_name == latest.c.table_name,
            LegacyImportRowStage.import_batch_id == latest.c.import_batch_id,
        )
        .correlate(latest)
        .scalar_subquery()
    )

    query = (
        select(
            latest.c.table_name,
            latest.c.id,
            latest.c.import_batch_id,
            latest.c.estimated_row_count,
            latest.c.actual_row_count,
            latest.c.error_count,
            latest.c.columns,
            latest.c.primary_key_columns,
            LegacyTableReviewState.id.label("review_id"),
            LegacyTableReviewState.decision.label("review_decision"),
            LegacyTableReviewState.notes.label("review_notes"),
            count_subq.label("staged_row_count"),
        )
        .outerjoin(
            LegacyTableReviewState,
            latest.c.table_name == LegacyTableReviewState.table_name,
        )
        .order_by(latest.c.table_name)
    )

    result = await db.execute(query)
    rows = result.all()

    tables = []
    for row in rows:
        tables.append(
            LegacyTableWithReviewResponse(
                table_name=row.table_name,
                estimated_row_count=row.estimated_row_count,
                actual_row_count=row.actual_row_count,
                error_count=row.error_count,
                columns=row.columns,
                primary_key_columns=row.primary_key_columns,
                import_batch_id=row.import_batch_id,
                manifest_id=row.id,
                review_id=row.review_id,
                review_decision=row.review_decision,
                review_notes=row.review_notes,
                staged_row_count=row.staged_row_count,
            )
        )

    return LegacyTableListResponse(tables=tables, total_tables=len(tables))


async def review_table(
    db: AsyncSession,
    table_name: str,
    payload: LegacyTableReviewRequest,
) -> LegacyTableReviewResponse:
    now = utcnow()

    review = await db.execute(
        select(LegacyTableReviewState).where(LegacyTableReviewState.table_name == table_name)
    )
    review = review.scalar_one_or_none()

    if payload.decision == TableReviewDecision.DELETE_STAGING.value:
        if not payload.confirm_delete:
            raise ValueError("confirm_delete must be True to delete stage rows for table '{table_name}'.")
        if review and review.deleted_at:
            raise ValueError(f"Table '{table_name}' has already been deleted from staging.")

        result = await db.execute(
            delete(LegacyImportRowStage).where(
                LegacyImportRowStage.source_table_name == table_name
            )
        )
        deleted_count = result.rowcount

        if review is None:
            review = LegacyTableReviewState(
                table_name=table_name,
                decision=TableReviewDecision.DELETE_STAGING.value,
                notes=payload.notes,
                decided_by=payload.decided_by,
                decided_at=now,
                deleted_at=now,
            )
            db.add(review)
        else:
            review.decision = TableReviewDecision.DELETE_STAGING.value
            review.notes = payload.notes or review.notes
            review.decided_by = payload.decided_by
            review.decided_at = now
            review.deleted_at = now

        await db.commit()
        await db.refresh(review)

        manifest = await db.execute(
            select(LegacyTableManifest)
            .where(LegacyTableManifest.table_name == table_name)
            .order_by(LegacyTableManifest.created_at.desc())
        )
        manifest = manifest.scalar_one_or_none()

        return LegacyTableReviewResponse(
            review=LegacyTableReviewStateResponse.model_validate(review),
            manifest=_manifest_response(manifest) if manifest else None,
            row_count=deleted_count,
        )

    if review is None:
        review = LegacyTableReviewState(
            table_name=table_name,
            decision=payload.decision,
            notes=payload.notes,
            decided_by=payload.decided_by,
            decided_at=now,
        )
        db.add(review)
    else:
        review.decision = payload.decision
        if payload.notes is not None:
            review.notes = payload.notes
        if payload.decided_by is not None:
            review.decided_by = payload.decided_by
        review.decided_at = now

    await db.commit()
    await db.refresh(review)

    manifest = await db.execute(
        select(LegacyTableManifest)
        .where(LegacyTableManifest.table_name == table_name)
        .order_by(LegacyTableManifest.created_at.desc())
    )
    manifest = manifest.scalar_one_or_none()

    staged_count = await db.execute(
        select(func.count(LegacyImportRowStage.id)).where(
            LegacyImportRowStage.source_table_name == table_name
        )
    )
    staged_count = staged_count.scalar() or 0

    return LegacyTableReviewResponse(
        review=LegacyTableReviewStateResponse.model_validate(review),
        manifest=_manifest_response(manifest) if manifest else None,
        row_count=staged_count,
    )


async def import_legacy_json_export(
    db: AsyncSession,
    export: LegacyJsonExportFile,
) -> LegacyJsonUploadResponse:
    batch = ImportBatch(
        source=ImportSource.LEGACY_MARIADB_JSON.value,
        status=ImportStatus.RUNNING.value,
        source_name=export.source_name,
        started_at=utcnow(),
        import_metadata={"exported_at": export.exported_at, "table_count": len(export.tables)},
    )
    db.add(batch)
    await db.flush()

    try:
        manifests: list[LegacyTableManifest] = []
        total_rows = 0
        total_errors = 0

        for table_def in export.tables:
            table_name = table_def.table_name
            col_names = [c["name"] for c in table_def.columns]
            pk_columns = table_def.primary_key_columns or []

            manifest = LegacyTableManifest(
                import_batch_id=batch.id,
                table_name=table_name,
                estimated_row_count=table_def.estimated_rows,
                columns=table_def.columns,
                primary_key_columns=pk_columns,
                import_started_at=utcnow(),
            )
            db.add(manifest)
            await db.flush()

            actual = 0
            errors = 0
            for i, row in enumerate(table_def.rows, start=1):
                try:
                    raw = {col: row.get(col) for col in col_names}
                    h = _row_hash(raw)
                    pk_value = _build_pk_value(raw, pk_columns) if pk_columns else None
                    db.add(
                        LegacyImportRowStage(
                            import_batch_id=batch.id,
                            table_manifest_id=manifest.id,
                            source_table_name=table_name,
                            source_primary_key_value=pk_value,
                            source_row_hash=h,
                            row_number=i,
                            column_names=col_names,
                            raw_payload=raw,
                            import_error=None,
                        )
                    )
                    actual += 1
                except Exception as exc:
                    errors += 1
                    db.add(
                        LegacyImportRowStage(
                            import_batch_id=batch.id,
                            table_manifest_id=manifest.id,
                            source_table_name=table_name,
                            source_primary_key_value=None,
                            source_row_hash="",
                            row_number=i,
                            column_names=col_names,
                            raw_payload={"_error": f"row processing failed: {exc}"},
                            import_error=str(exc),
                        )
                    )

                if (actual + errors) % 500 == 0:
                    await db.flush()

            manifest.actual_row_count = actual
            manifest.error_count = errors
            manifest.import_completed_at = utcnow()
            manifests.append(manifest)
            total_rows += actual
            total_errors += errors

        batch.status = ImportStatus.COMPLETED.value
        batch.completed_at = utcnow()
        batch.row_count = total_rows
        batch.error_count = total_errors
        await db.commit()
        await db.refresh(batch)
        return LegacyJsonUploadResponse(
            batch=_batch_response(batch),
            manifests=[_manifest_response(m) for m in manifests],
            total_rows=total_rows,
        )
    except Exception as exc:
        batch.status = ImportStatus.FAILED.value
        batch.error_count = 1
        batch.error_message = str(exc)
        batch.completed_at = utcnow()
        await db.commit()
        raise


async def delete_table_staging(
    db: AsyncSession,
    table_name: str,
    confirm: bool = False,
) -> LegacyTableDeleteResponse:
    if not confirm:
        raise ValueError("Must set confirm=True to delete staging rows for table '{table_name}'.")

    review = await db.execute(
        select(LegacyTableReviewState).where(LegacyTableReviewState.table_name == table_name)
    )
    review = review.scalar_one_or_none()
    if review and review.deleted_at:
        raise ValueError(f"Table '{table_name}' has already been deleted from staging.")

    result = await db.execute(
        delete(LegacyImportRowStage).where(
            LegacyImportRowStage.source_table_name == table_name
        )
    )
    deleted = result.rowcount

    now = utcnow()
    if review is None:
        review = LegacyTableReviewState(
            table_name=table_name,
            decision=TableReviewDecision.DELETE_STAGING.value,
            decided_at=now,
            deleted_at=now,
        )
        db.add(review)
    else:
        review.decision = TableReviewDecision.DELETE_STAGING.value
        review.decided_at = now
        review.deleted_at = now

    await db.commit()
    return LegacyTableDeleteResponse(table_name=table_name, rows_deleted=deleted, review_reset=True)
