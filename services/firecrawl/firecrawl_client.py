"""Firecrawl client wrapper for the Trend Scout microservice.

A thin wrapper around Firecrawl v2 endpoints. Phase 8 wires this client to
the standard tier targets (Cults3D, Thangs, STLFinder, CGTrader,
MyMiniFactory trending fallback, general). Phase 9 adds the Etsy tier with
random throttling.

The official ``firecrawl-py`` SDK is small and we depend on it through
``services/trend-scout/pyproject.toml``. This module is the integration glue
that turns a Firecrawl response into a ``ScoutResult``-shaped dict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FirecrawlClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 30.0
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as client:
                response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Firecrawl error: %s %s -> %s", method, path, exc)
            return {"success": False, "error": str(exc)}
        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "status": response.status_code,
            }
        try:
            return response.json()
        except ValueError:
            return {"success": False, "error": "invalid JSON response"}

    def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
        extract_schema: dict[str, Any] | None = None,
        only_main_content: bool = True,
        wait_for_ms: int | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "url": url,
            "formats": formats or ["markdown"],
            "onlyMainContent": only_main_content,
            "timeout": timeout_ms,
        }
        if extract_schema is not None:
            body["extract"] = {"schema": extract_schema}
        if wait_for_ms is not None:
            body["waitFor"] = wait_for_ms
        return self._request("POST", "/v2/scrape", json=body)

    def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v2/search",
            json={"query": query, "limit": limit},
        )


def _scrape_schema() -> dict[str, Any]:
    """Default schema for trending-page scrapes across all Firecrawl targets.

    Targets return a uniform shape: title, url, price (optional), thumbnail
    (optional), likes, downloads, prints_count, designer, category.
    """
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "price": {"type": "string"},
            "thumbnail": {"type": "string"},
            "likes": {"type": "integer"},
            "downloads": {"type": "integer"},
            "prints_count": {"type": "integer"},
            "designer": {"type": "string"},
            "category": {"type": "string"},
        },
        "required": ["title", "url"],
    }


def scrape_trending(
    client: FirecrawlClient,
    target_url: str,
    source: str,
    keyword: str,
    target_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scrape a trending page and return a ScoutResult-shaped dict."""
    target_meta = target_meta or {}
    response = client.scrape(
        target_url,
        formats=["extract"],
        extract_schema=_scrape_schema(),
        only_main_content=True,
        timeout_ms=30000,
    )

    if not response.get("success", False):
        errors = [response.get("error", "unknown firecrawl error")]
        return {
            "source": source,
            "keyword_or_category": keyword,
            "items": [],
            "errors": errors,
            "metadata": {"target_url": target_url, **(target_meta or {})},
        }

    data = response.get("data") or {}
    extracted = data.get("extract") if isinstance(data, dict) else None
    items = []
    if isinstance(extracted, dict):
        items.append(
            {
                "title": extracted.get("title") or keyword,
                "url": extracted.get("url") or target_url,
                "thumbnail": extracted.get("thumbnail", ""),
                "price": extracted.get("price"),
                "likes": int(extracted.get("likes") or 0),
                "downloads": int(extracted.get("downloads") or 0),
                "prints_count": int(extracted.get("prints_count") or 0),
                "designer": extracted.get("designer", ""),
                "category": extracted.get("category", ""),
            }
        )
    elif isinstance(extracted, list):
        for entry in extracted:
            if not isinstance(entry, dict):
                continue
            items.append(
                {
                    "title": entry.get("title") or keyword,
                    "url": entry.get("url") or "",
                    "thumbnail": entry.get("thumbnail", ""),
                    "price": entry.get("price"),
                    "likes": int(entry.get("likes") or 0),
                    "downloads": int(entry.get("downloads") or 0),
                    "prints_count": int(entry.get("prints_count") or 0),
                    "designer": entry.get("designer", ""),
                    "category": entry.get("category", ""),
                }
            )

    return {
        "source": source,
        "keyword_or_category": keyword,
        "items": items,
        "errors": [],
        "metadata": {"target_url": target_url, **(target_meta or {})},
    }
