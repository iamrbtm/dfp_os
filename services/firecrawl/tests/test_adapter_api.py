from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from firecrawl.main import app


def _client(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    return TestClient(app)


def test_health(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_scrape_requires_token(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/v2/scrape", json={"url": "https://example.com"})
    assert response.status_code == 401


def test_scrape_blocks_internal_url(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/v2/scrape",
        headers={"Authorization": "Bearer test-key"},
        json={"url": "http://localhost:8093"},
    )
    assert response.status_code == 422


def test_scrape_returns_markdown_and_extract(monkeypatch) -> None:
    client = _client(monkeypatch)
    response_mock = MagicMock()
    response_mock.content = (
        b"<html><title>Trending</title><a href='/dragon'>Rainbow Dragon</a></html>"
    )
    response_mock.encoding = "utf-8"
    response_mock.raise_for_status = MagicMock()

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = None
    async_client.get.return_value = response_mock

    with patch("firecrawl.main.httpx.AsyncClient", return_value=async_client):
        response = client.post(
            "/v2/scrape",
            headers={"Authorization": "Bearer test-key"},
            json={"url": "https://example.com/trending", "formats": ["extract"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["extract"][0]["title"] == "Rainbow Dragon"


def test_search_is_intentionally_disabled(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/v2/search",
        headers={"Authorization": "Bearer test-key"},
        json={"query": "3D printed dragon", "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert "disabled" in response.json()["warning"]
