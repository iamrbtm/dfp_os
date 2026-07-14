import pytest


@pytest.mark.asyncio
async def test_alias_mapping_create_list_and_review(client, auth_headers):
    create_response = await client.post(
        "/api/v1/mappings",
        headers=auth_headers,
        json={
            "source": "square_csv",
            "entity_type": "product",
            "source_value": "Dragon - Tiny",
            "target_entity_type": "product",
            "target_entity_id": "product-123",
            "target_display_name": "Tiny Dragon",
            "match_confidence": "0.7000",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["normalized_value"] == "dragon - tiny"
    assert created["reviewed"] is False

    list_response = await client.get("/api/v1/mappings?reviewed=false", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    review_response = await client.post(
        f"/api/v1/mappings/{created['id']}/review",
        headers=auth_headers,
        json={
            "target_entity_type": "variant",
            "target_entity_id": "variant-456",
            "target_display_name": "Tiny Dragon - Regular",
            "match_confidence": "0.9500",
            "reviewed_by": "admin-user",
            "notes": "Confirmed from Product Studio SKU mapping.",
        },
    )
    assert review_response.status_code == 200
    reviewed = review_response.json()
    assert reviewed["reviewed"] is True
    assert reviewed["reviewed_by"] == "admin-user"
    assert reviewed["target_entity_id"] == "variant-456"
