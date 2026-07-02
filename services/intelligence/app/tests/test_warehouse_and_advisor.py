from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import MarketAdvisorRecommendation, ProductSalesSummary, SalesFactLine, SeasonalProductPerformance


async def _import_sample_square(client, auth_headers):
    sample = Path("app/tests/fixtures/square_items_sample.csv").read_bytes()
    response = await client.post(
        "/api/v1/imports/square/items-csv",
        headers=auth_headers,
        files={"file": ("square.csv", sample, "text/csv")},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_square_warehouse_rebuild_creates_facts_and_summaries(client, auth_headers, async_session):
    await _import_sample_square(client, auth_headers)

    response = await client.post("/api/v1/warehouse/rebuild-square", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["fact_rows"] == 2
    assert payload["product_summary_rows"] == 2
    assert payload["seasonal_summary_rows"] == 2
    assert payload["channel_summary_rows"] == 1

    facts = (await async_session.execute(select(SalesFactLine))).scalars().all()
    assert len(facts) == 2
    assert facts[0].product_name == "Dragon - Tiny"

    products = (await async_session.execute(select(ProductSalesSummary))).scalars().all()
    assert {product.product_name for product in products} == {"Dragon - Tiny", "Fidget Slider"}

    seasonal = (await async_session.execute(select(SeasonalProductPerformance))).scalars().all()
    assert {row.sale_month for row in seasonal} == {9}

    list_response = await client.get("/api/v1/warehouse/products", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["product_name"] == "Dragon - Tiny"


@pytest.mark.asyncio
async def test_market_advisor_generates_deterministic_recommendations(client, auth_headers, async_session):
    await _import_sample_square(client, auth_headers)
    rebuild = await client.post("/api/v1/warehouse/rebuild-square", headers=auth_headers)
    assert rebuild.status_code == 200

    response = await client.post(
        "/api/v1/advisor/market",
        headers=auth_headers,
        json={
            "market_name": "Fall Family Market",
            "market_date": "2026-09-12",
            "event_type": "family",
            "inventory_by_product_key": {"dragon-tiny": 1},
            "max_products": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_name"] == "Fall Family Market"
    assert len(payload["recommendations"]) == 2
    top = payload["recommendations"][0]
    assert top["product_name"] == "Dragon - Tiny"
    assert top["suggested_quantity"] >= 3
    assert top["suggested_print_quantity"] >= 2
    assert top["expected_revenue_cents"] >= 1000
    assert top["evidence"]["seasonal_summary"]["sale_month"] == 9

    stored = (await async_session.execute(select(MarketAdvisorRecommendation))).scalars().all()
    assert len(stored) == 2
