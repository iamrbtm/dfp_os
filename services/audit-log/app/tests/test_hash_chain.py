import pytest


@pytest.mark.asyncio
async def test_hash_is_created(client, auth_headers, sample_event):
    response = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    data = response.json()
    assert data["hash"] != ""
    assert len(data["hash"]) == 64


@pytest.mark.asyncio
async def test_hash_chain_linking(client, auth_headers, sample_event):
    resp1 = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    resp2 = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    assert resp2.json()["previous_hash"] == resp1.json()["hash"]


@pytest.mark.asyncio
async def test_verify_chain_valid(client, auth_headers, sample_event):
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    response = await client.post(
        "/api/v1/audit-events/verify-chain",
        json={},
        headers=auth_headers,
    )
    data = response.json()
    assert data["valid"] is True
    assert data["checked_count"] >= 2


@pytest.mark.asyncio
async def test_verify_chain_detects_tampering(client, auth_headers, sample_event, async_session):
    resp = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    event_id = resp.json()["id"]
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)

    from app.models import AuditEvent
    result = await async_session.get(AuditEvent, event_id)
    result.action = "tampered.action"
    await async_session.commit()

    response = await client.post(
        "/api/v1/audit-events/verify-chain",
        json={},
        headers=auth_headers,
    )
    data = response.json()
    assert data["valid"] is False
    assert data["first_invalid_event_id"] == event_id
