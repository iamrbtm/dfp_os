"""Tests for the Firecrawl client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.firecrawl.firecrawl_client import FirecrawlClient, scrape_trending


@pytest.fixture
def client() -> FirecrawlClient:
    return FirecrawlClient(
        base_url="http://firecrawl:3002", api_key="test-key"
    )


def _make_response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    if payload is None:
        response.content = b""
    else:
        response.content = b"{}"
        response.json = lambda: payload
    return response


def test_scrape_returns_payload(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(
        return_value=_make_response(
            200, {"success": True, "data": {"extract": {"title": "Dragon"}}}
        )
    )

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        result = client.scrape("https://example.com/x")

    assert result["success"] is True
    args, kwargs = fake.request.call_args
    assert kwargs["json"]["url"] == "https://example.com/x"


def test_scrape_handles_network_error(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(side_effect=httpx.ConnectError("boom"))

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        result = client.scrape("https://example.com/x")

    assert result["success"] is False
    assert "boom" in result["error"]


def test_scrape_handles_http_error(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(return_value=_make_response(503))

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        result = client.scrape("https://example.com/x")

    assert result["success"] is False
    assert result["status"] == 503


def test_search_payload_shape(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(
        return_value=_make_response(200, {"success": True, "data": []})
    )

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        client.search("3D printed dragon", limit=5)

    args, kwargs = fake.request.call_args
    assert args[1] == "/v2/search"
    assert kwargs["json"]["query"] == "3D printed dragon"
    assert kwargs["json"]["limit"] == 5


def test_scrape_trending_returns_extracted_items(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(
        return_value=_make_response(
            200,
            {
                "success": True,
                "data": {
                    "extract": {
                        "title": "Rainbow Dragon",
                        "url": "https://example.com/dragon",
                        "likes": 100,
                        "downloads": 50,
                        "prints_count": 30,
                    }
                },
            },
        )
    )

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        result = scrape_trending(
            client,
            target_url="https://example.com/trending",
            source="cults3d",
            keyword="dragon",
            target_meta={"page": 1},
        )

    assert result["source"] == "cults3d"
    assert result["keyword_or_category"] == "dragon"
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Rainbow Dragon"
    assert result["items"][0]["likes"] == 100
    assert result["metadata"]["page"] == 1


def test_scrape_trending_handles_failure(client: FirecrawlClient) -> None:
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.request = MagicMock(
        return_value=_make_response(503)
    )

    with patch("services.firecrawl.firecrawl_client.httpx.Client", return_value=fake):
        result = scrape_trending(
            client,
            target_url="https://example.com/trending",
            source="cults3d",
            keyword="dragon",
        )

    assert result["source"] == "cults3d"
    assert result["items"] == []
    assert result["errors"]
    assert "503" in result["errors"][0]
