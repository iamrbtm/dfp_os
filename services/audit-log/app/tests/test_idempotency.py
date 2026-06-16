import pytest


@pytest.mark.asyncio
async def test_idempotency_returns_existing_event(client, auth_headers, sample_event):
    event = {**sample_event, "idempotency_key": "unique-key-123"}
    resp1 = await client.post("/api/v1/audit-events", json=event, headers=auth_headers)
    resp2 = await client.post("/api/v1/audit-events", json=event, headers=auth_headers)
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_batch(client, auth_headers, sample_event):
    event_a = {**sample_event, "idempotency_key": "batch-key-a"}
    event_b = {**sample_event, "idempotency_key": "batch-key-b"}
    payload = {"events": [event_a, event_b, event_a]}
    response = await client.post("/api/v1/audit-events/batch", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["total"] == 3
    assert data["created"][0]["id"] == data["created"][2]["id"]
