import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from app.main import create_app
from app.models import (
    LegacyImportRowStage,
    LegacyTableManifest,
    LegacyTableReviewState,
    TableReviewDecision,
    ImportBatch,
    ImportSource,
    LegacyMariaDbTableSnapshot,
)
from app.schemas.imports import (
    LegacyImportAllRequest,
    LegacyImportAllResponse,
    LegacyTableReviewRequest,
)

MOCK_SCHEMA = [
    {
        "table_name": "products",
        "estimated_rows": 5,
        "columns": [
            {"name": "id", "data_type": "int", "nullable": False, "key": "PRI"},
            {"name": "name", "data_type": "varchar", "nullable": True, "key": ""},
            {"name": "price", "data_type": "decimal", "nullable": True, "key": ""},
        ],
        "primary_key_columns": ["id"],
    },
    {
        "table_name": "orders",
        "estimated_rows": 10,
        "columns": [
            {"name": "order_id", "data_type": "int", "nullable": False, "key": "PRI"},
            {"name": "customer", "data_type": "varchar", "nullable": True, "key": ""},
            {"name": "total", "data_type": "decimal", "nullable": True, "key": ""},
        ],
        "primary_key_columns": ["order_id"],
    },
]

MOCK_ROWS = {
    "products": [
        {"id": 1, "name": "Widget", "price": "9.99"},
        {"id": 2, "name": "Gadget", "price": "14.99"},
        {"id": 3, "name": "Doohickey", "price": "4.99"},
    ],
    "orders": [
        {"order_id": 100, "customer": "Alice", "total": "29.97"},
        {"order_id": 101, "customer": "Bob", "total": "14.99"},
    ],
}


@pytest.fixture()
def app():
    return create_app()


@pytest.mark.asyncio
async def test_import_all_tables_persists_manifests_and_rows(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        response = await import_all_legacy_tables(
            async_session, payload, schema_rows=MOCK_SCHEMA
        )

    assert response.batch.status == "completed"
    assert response.batch.row_count == 5
    assert len(response.manifests) == 2

    manifest_names = {m.table_name for m in response.manifests}
    assert manifest_names == {"products", "orders"}

    for m in response.manifests:
        assert m.actual_row_count > 0
        assert m.import_completed_at is not None

    rows = (await async_session.execute(select(LegacyImportRowStage))).scalars().all()
    assert len(rows) == 5

    product_rows = [r for r in rows if r.source_table_name == "products"]
    assert len(product_rows) == 3

    order_rows = [r for r in rows if r.source_table_name == "orders"]
    assert len(order_rows) == 2

    for r in rows:
        assert r.source_row_hash != ""
        assert r.raw_payload is not None
        assert r.column_names is not None


@pytest.mark.asyncio
async def test_import_preserves_raw_payloads(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        response = await import_all_legacy_tables(
            async_session, payload, schema_rows=MOCK_SCHEMA
        )

    rows = (await async_session.execute(select(LegacyImportRowStage))).scalars().all()

    product_1 = next(r for r in rows if r.source_table_name == "products" and r.row_number == 1)
    assert product_1.raw_payload["id"] == 1
    assert product_1.raw_payload["name"] == "Widget"
    assert product_1.source_primary_key_value == "1"
    assert product_1.column_names == ["id", "name", "price"]


@pytest.mark.asyncio
async def test_import_handles_empty_table(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables

    empty_schema = [
        {
            "table_name": "empty_table",
            "estimated_rows": 0,
            "columns": [{"name": "id", "data_type": "int", "nullable": False, "key": "PRI"}],
            "primary_key_columns": ["id"],
        }
    ]

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload, extra_empty=["empty_table"]):
        response = await import_all_legacy_tables(
            async_session, payload, schema_rows=empty_schema
        )

    assert response.batch.status == "completed"
    assert len(response.manifests) == 1
    assert response.manifests[0].actual_row_count == 0

    rows = (await async_session.execute(select(LegacyImportRowStage))).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_review_keep_table(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, review_table

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    review_payload = LegacyTableReviewRequest(
        decision="keep",
        notes="This table has useful product data.",
        decided_by="test_user",
    )

    response = await review_table(async_session, "products", review_payload)

    assert response.review.decision == "keep"
    assert response.review.notes == "This table has useful product data."
    assert response.review.decided_by == "test_user"
    assert response.manifest is not None
    assert response.row_count == 3

    reviews = (await async_session.execute(select(LegacyTableReviewState))).scalars().all()
    assert len(reviews) == 1
    assert reviews[0].table_name == "products"
    assert reviews[0].decision == "keep"


@pytest.mark.asyncio
async def test_review_exclude_table(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, review_table

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    review_payload = LegacyTableReviewRequest(
        decision="exclude",
        notes="Temporary data, not needed.",
    )

    response = await review_table(async_session, "orders", review_payload)
    assert response.review.decision == "exclude"

    reviews = (await async_session.execute(select(LegacyTableReviewState))).scalars().all()
    assert len(reviews) == 1
    assert reviews[0].table_name == "orders"


@pytest.mark.asyncio
async def test_delete_staging_requires_confirm(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, review_table

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    with pytest.raises(ValueError, match="confirm_delete must be True"):
        await review_table(
            async_session,
            "products",
            LegacyTableReviewRequest(decision="delete_staging"),
        )


@pytest.mark.asyncio
async def test_delete_staging_removes_rows(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, delete_table_staging

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    result = await delete_table_staging(async_session, "products", confirm=True)

    assert result.table_name == "products"
    assert result.rows_deleted == 3
    assert result.review_reset is True

    rows = (await async_session.execute(select(LegacyImportRowStage))).scalars().all()
    assert len(rows) == 2
    assert all(r.source_table_name == "orders" for r in rows)

    review = (
        await async_session.execute(
            select(LegacyTableReviewState).where(LegacyTableReviewState.table_name == "products")
        )
    ).scalar_one_or_none()
    assert review is not None
    assert review.decision == "delete_staging"
    assert review.deleted_at is not None


@pytest.mark.asyncio
async def test_list_imported_tables(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, list_imported_tables

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    result = await list_imported_tables(async_session)
    assert result.total_tables == 2

    table_names = {t.table_name for t in result.tables}
    assert table_names == {"products", "orders"}

    products = next(t for t in result.tables if t.table_name == "products")
    assert products.actual_row_count == 3
    assert len(products.columns) == 3
    assert products.primary_key_columns == ["id"]


@pytest.mark.asyncio
async def test_import_all_api_endpoint_needs_credentials(async_session, auth_headers, monkeypatch):
    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_host", None)
    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_database", None)
    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_user", None)
    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_password", None)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/imports/legacy-mariadb/import-all",
            json={
                "host": "",
                "database": "",
                "user": "",
                "password": "",
                "batch_size": 100,
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        data = response.json()
        assert "Missing legacy MariaDB connection settings" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_config_fails_without_credentials(async_session, monkeypatch):
    from app.services.legacy_mariadb import resolve_legacy_config

    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_host", None)
    with pytest.raises(ValueError, match="Missing legacy MariaDB connection settings"):
        resolve_legacy_config(host=None, database=None, user=None, password=None)


@pytest.mark.asyncio
async def test_import_then_review_api(async_session, auth_headers):
    from app.services.legacy_mariadb import import_all_legacy_tables

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get(
            "/api/v1/imports/legacy-mariadb/tables",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total_tables"] == 2

        review_resp = await client.post(
            "/api/v1/imports/legacy-mariadb/tables/products/review",
            json={"decision": "keep", "notes": "Good data", "decided_by": "admin"},
            headers=auth_headers,
        )
        assert review_resp.status_code == 200
        review_data = review_resp.json()
        assert review_data["review"]["decision"] == "keep"
        assert review_data["review"]["table_name"] == "products"

        get_review_resp = await client.get(
            "/api/v1/imports/legacy-mariadb/tables/products/review",
            headers=auth_headers,
        )
        assert get_review_resp.status_code == 200
        assert get_review_resp.json()["decision"] == "keep"


@pytest.mark.asyncio
async def test_double_delete_raises(async_session):
    from app.services.legacy_mariadb import import_all_legacy_tables, delete_table_staging

    payload = LegacyImportAllRequest(
        host="legacy.example.test",
        database="test_db",
        user="readonly",
        password="secret",
        batch_size=100,
    )

    with _patch_legacy_fetch(payload):
        await import_all_legacy_tables(async_session, payload, schema_rows=MOCK_SCHEMA)

    await delete_table_staging(async_session, "products", confirm=True)

    with pytest.raises(ValueError, match="already been deleted"):
        await delete_table_staging(async_session, "products", confirm=True)


@pytest.mark.asyncio
async def test_json_upload_imports_rows(async_session):
    from app.services.legacy_mariadb import import_legacy_json_export
    from app.schemas.imports import LegacyJsonExportFile

    export = LegacyJsonExportFile(
        source_name="test_db",
        exported_at="2026-07-02T12:00:00Z",
        tables=[
            {
                "table_name": "products",
                "estimated_rows": 3,
                "primary_key_columns": ["id"],
                "columns": [
                    {"name": "id", "data_type": "int", "nullable": False, "key": "PRI"},
                    {"name": "name", "data_type": "varchar", "nullable": True, "key": ""},
                    {"name": "price", "data_type": "decimal", "nullable": True, "key": ""},
                ],
                "rows": [
                    {"id": 1, "name": "Widget", "price": "9.99"},
                    {"id": 2, "name": "Gadget", "price": "14.99"},
                ],
            },
            {
                "table_name": "orders",
                "estimated_rows": 1,
                "primary_key_columns": ["order_id"],
                "columns": [
                    {"name": "order_id", "data_type": "int", "nullable": False, "key": "PRI"},
                    {"name": "customer", "data_type": "varchar", "nullable": True, "key": ""},
                ],
                "rows": [
                    {"order_id": 100, "customer": "Alice"},
                ],
            },
        ],
    )

    response = await import_legacy_json_export(async_session, export)

    assert response.batch.status == "completed"
    assert response.total_rows == 3
    assert len(response.manifests) == 2

    manifest_names = {m.table_name for m in response.manifests}
    assert manifest_names == {"products", "orders"}

    rows = (await async_session.execute(select(LegacyImportRowStage))).scalars().all()
    assert len(rows) == 3

    product_rows = [r for r in rows if r.source_table_name == "products"]
    assert len(product_rows) == 2
    assert product_rows[0].raw_payload["name"] == "Widget"
    assert product_rows[0].source_primary_key_value == "1"
    assert product_rows[1].source_primary_key_value == "2"


@pytest.mark.asyncio
async def test_json_upload_api_endpoint(async_session, auth_headers):
    import json

    export_data = {
        "source_name": "test_db",
        "exported_at": "2026-07-02T12:00:00Z",
        "tables": [
            {
                "table_name": "products",
                "columns": [
                    {"name": "id", "data_type": "int", "nullable": False, "key": "PRI"},
                    {"name": "name", "data_type": "varchar", "nullable": True, "key": ""},
                ],
                "rows": [
                    {"id": 1, "name": "Widget"},
                ],
            }
        ],
    }

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/imports/legacy-mariadb/upload-json",
            files={"file": ("export.json", json.dumps(export_data), "application/json")},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["batch"]["status"] == "completed"
        assert data["total_rows"] == 1
        assert len(data["manifests"]) == 1
        assert data["manifests"][0]["table_name"] == "products"


@pytest.mark.asyncio
async def test_json_upload_rejects_non_json(async_session, auth_headers):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/imports/legacy-mariadb/upload-json",
            files={"file": ("export.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400


# ---- helpers ----

def _patch_legacy_fetch(payload, extra_empty=None):
    import unittest.mock as mock

    def fake_fetch_schema(config):
        return MOCK_SCHEMA

    def fake_import_rows(config, table_def, batch_id, manifest_id, batch_size=500):
        table_name = table_def["table_name"]
        col_names = [c["name"] for c in table_def["columns"]]
        pk_cols = table_def.get("primary_key_columns", [])

        rows = MOCK_ROWS.get(table_name, [])
        if extra_empty and table_name in extra_empty:
            rows = []

        for i, row in enumerate(rows, start=1):
            raw = {col: row.get(col) for col in col_names}
            import hashlib, json
            joined = "\x1f".join(f"{k}={json.dumps(raw.get(k), default=str)}" for k in sorted(raw))
            h = hashlib.sha256(joined.encode("utf-8")).hexdigest()
            pk_value = "|".join(str(row.get(c, "NULL")) for c in pk_cols) if pk_cols else None
            yield {
                "import_batch_id": batch_id,
                "table_manifest_id": manifest_id,
                "source_table_name": table_name,
                "source_primary_key_value": pk_value,
                "source_row_hash": h,
                "row_number": i,
                "column_names": col_names,
                "raw_payload": raw,
                "import_error": None,
            }

    return mock.patch.multiple(
        "app.services.legacy_mariadb",
        fetch_legacy_schema=fake_fetch_schema,
        _import_table_rows=fake_import_rows,
    )
