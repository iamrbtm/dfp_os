from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import SquareItemRaw


@pytest.mark.asyncio
async def test_square_csv_import_sanitizes_payment_sensitive_fields(client, auth_headers, async_session):
    sample = Path("app/tests/fixtures/square_items_sample.csv").read_bytes()

    response = await client.post(
        "/api/v1/imports/square/items-csv",
        headers=auth_headers,
        files={"file": ("square.csv", sample, "text/csv")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["imported_rows"] == 2
    assert payload["rejected_rows"] == 0
    assert payload["sensitive_fields_removed"] == ["PAN Suffix", "Token"]
    assert payload["batch"]["status"] == "completed"

    rows = (await async_session.execute(select(SquareItemRaw).order_by(SquareItemRaw.row_number))).scalars().all()
    assert len(rows) == 2
    assert rows[0].net_sales_cents == 1000
    assert rows[1].discounts_cents == 100
    assert rows[0].sensitive_fields_present is True
    assert "Token" not in rows[0].raw_payload
    assert "PAN Suffix" not in rows[0].raw_payload


@pytest.mark.asyncio
async def test_square_csv_import_rejects_missing_required_columns(client, auth_headers):
    response = await client.post(
        "/api/v1/imports/square/items-csv",
        headers=auth_headers,
        files={"file": ("bad.csv", b"Date,Item\n2025-01-01,Dragon\n", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_square_csv"
