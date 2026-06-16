import pytest


@pytest.mark.asyncio
async def test_create_audit_event(client, auth_headers, sample_event):
    response = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "hash" in data
    assert data["hash"] != ""
    assert data["previous_hash"] is None


@pytest.mark.asyncio
async def test_create_audit_event_requires_auth(client, sample_event):
    response = await client.post("/api/v1/audit-events", json=sample_event)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_audit_event_invalid_token(client, sample_event):
    headers = {"Authorization": "Bearer invalid"}
    response = await client.post("/api/v1/audit-events", json=sample_event, headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_audit_event_missing_required(client, auth_headers):
    response = await client.post("/api/v1/audit-events", json={}, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_batch_create_audit_events(client, auth_headers, sample_event):
    payload = {"events": [sample_event, sample_event]}
    response = await client.post("/api/v1/audit-events/batch", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["total"] == 2
    assert len(data["created"]) == 2


@pytest.mark.asyncio
async def test_batch_exceeds_max(client, auth_headers, sample_event):
    payload = {"events": [sample_event] * 101}
    response = await client.post("/api/v1/audit-events/batch", json=payload, headers=auth_headers)
    assert response.status_code == 422
