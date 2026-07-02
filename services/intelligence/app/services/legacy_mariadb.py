from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ImportBatch, ImportSource, ImportStatus, LegacyMariaDbTableSnapshot, utcnow
from app.schemas.imports import (
    ImportBatchResponse,
    LegacyMariaDbInspectRequest,
    LegacyMariaDbInspectResponse,
    LegacyMariaDbTableResponse,
)


@dataclass(frozen=True)
class LegacyMariaDbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int


def resolve_legacy_config(payload: LegacyMariaDbInspectRequest) -> LegacyMariaDbConfig:
    host = payload.host or settings.legacy_mariadb_host
    database = payload.database or settings.legacy_mariadb_database
    user = payload.user or settings.legacy_mariadb_user
    password = payload.password or settings.legacy_mariadb_password
    port = payload.port or settings.legacy_mariadb_port
    connect_timeout = payload.connect_timeout or settings.legacy_mariadb_connect_timeout
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


def fetch_legacy_schema(config: LegacyMariaDbConfig) -> list[dict[str, Any]]:
    import pymysql

    conn = pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connect_timeout=config.connect_timeout,
        cursorclass=pymysql.cursors.DictCursor,
    )
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


async def inspect_legacy_mariadb(
    db: AsyncSession,
    payload: LegacyMariaDbInspectRequest,
    schema_rows: list[dict[str, Any]] | None = None,
) -> LegacyMariaDbInspectResponse:
    config = resolve_legacy_config(payload)
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
