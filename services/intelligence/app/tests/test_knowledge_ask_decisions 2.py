from pathlib import Path

import pytest


async def _seed_warehouse(client, auth_headers):
    sample = Path("app/tests/fixtures/square_items_sample.csv").read_bytes()
    response = await client.post(
        "/api/v1/imports/square/items-csv",
        headers=auth_headers,
        files={"file": ("square.csv", sample, "text/csv")},
    )
    assert response.status_code == 201
    rebuild = await client.post("/api/v1/warehouse/rebuild-square", headers=auth_headers)
    assert rebuild.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_document_search_and_ask_dfp(client, auth_headers):
    await _seed_warehouse(client, auth_headers)
    create = await client.post(
        "/api/v1/knowledge/documents",
        headers=auth_headers,
        json={
            "source": "manual",
            "title": "Fall market note",
            "document_type": "market_note",
            "source_ref": "market-1",
            "content": "Kids loved tiny dragons and fidget sliders. Wind made tall displays risky.",
            "metadata": {"weather": "windy"},
        },
    )
    assert create.status_code == 201

    search = await client.get("/api/v1/knowledge/search?q=tiny+dragons+wind", headers=auth_headers)
    assert search.status_code == 200
    assert search.json()["items"][0]["title"] == "Fall market note"

    ask = await client.post(
        "/api/v1/ask",
        headers=auth_headers,
        json={"question": "What should I bring if kids liked tiny dragons?", "limit": 3},
    )
    assert ask.status_code == 200
    payload = ask.json()
    assert "Top historical product signal" in payload["answer"]
    assert {item["tool"] for item in payload["evidence"]} >= {"product_summary", "knowledge_search"}


@pytest.mark.asyncio
async def test_decision_outcome_records_feedback(client, auth_headers):
    response = await client.post(
        "/api/v1/decision-outcomes",
        headers=auth_headers,
        json={
            "recommendation_id": "rec-1",
            "run_id": "run-1",
            "decision_type": "market_advisor",
            "user_action": "accepted",
            "outcome_status": "worked",
            "actual_units": 12,
            "actual_revenue_cents": 6000,
            "created_by": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["actual_units"] == 12

    listing = await client.get("/api/v1/decision-outcomes", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()["items"][0]["outcome_status"] == "worked"
