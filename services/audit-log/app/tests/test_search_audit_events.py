import pytest


@pytest.mark.asyncio
async def test_search_audit_events(client, auth_headers, sample_event):
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    response = await client.get("/api/v1/audit-events?action=test.action", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_audit_event_by_id(client, auth_headers, sample_event):
    create_resp = await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    event_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/audit-events/{event_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == event_id


@pytest.mark.asyncio
async def test_get_audit_event_not_found(client, auth_headers):
    response = await client.get("/api/v1/audit-events/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_entity_timeline(client, auth_headers, sample_event):
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    response = await client.get("/api/v1/entities/test_entity/entity-123/timeline", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_actor_timeline(client, auth_headers, sample_event):
    await client.post("/api/v1/audit-events", json=sample_event, headers=auth_headers)
    response = await client.get("/api/v1/actors/user-123/timeline", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1
