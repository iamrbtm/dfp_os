from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl

APP_NAME = "dfpos-firecrawl-adapter"
MAX_RESPONSE_BYTES = int(os.getenv("FIRECRAWL_ADAPTER_MAX_RESPONSE_BYTES", "1500000"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("FIRECRAWL_ADAPTER_TIMEOUT_SECONDS", "20"))
USER_AGENT = os.getenv(
    "FIRECRAWL_ADAPTER_USER_AGENT",
    "DFPosTrendScout/0.1 (+internal research; contact Dude Fish Printing)",
)

app = FastAPI(title=APP_NAME, version="0.1.0")


class ScrapeRequest(BaseModel):
    url: HttpUrl
    formats: list[str] = Field(default_factory=lambda: ["markdown"])
    only_main_content: bool = Field(default=True, alias="onlyMainContent")
    timeout_ms: int = Field(default=30000, alias="timeout")
    extract: dict[str, Any] | None = None
    wait_for_ms: int | None = Field(default=None, alias="waitFor")


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=25)


def _configured_api_key() -> str:
    return os.getenv("FIRECRAWL_API_KEY", "")


def _check_auth(request: Request) -> None:
    expected = _configured_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "api_key_not_configured", "message": "FIRECRAWL_API_KEY is not set."},
        )
    header = request.headers.get("Authorization", "")
    if header != f"Bearer {expected}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid Firecrawl adapter token."},
        )


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail={"code": "invalid_url"})
    host = parsed.hostname.lower()
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host in blocked or host.endswith(".local"):
        raise HTTPException(status_code=422, detail={"code": "blocked_internal_url"})
    return url


def _text_from_html(html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    links: list[dict[str, str]] = []
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).split())
        if label:
            links.append({"title": label[:180], "url": str(link["href"])})
    text = "\n".join(part for part in [title, soup.get_text("\n", strip=True)] if part)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:50000], links[:100]


def _extract_items(markdown: str, links: list[dict[str, str]], source_url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in links:
        title = entry.get("title", "").strip()
        href = entry.get("url", "").strip()
        if not title or len(title) < 3:
            continue
        if href.startswith("/"):
            parsed = urlparse(source_url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"
        items.append(
            {
                "title": title,
                "url": href or source_url,
                "price": None,
                "thumbnail": "",
                "likes": 0,
                "downloads": 0,
                "prints_count": 0,
                "designer": "",
                "category": "",
            }
        )
        if len(items) >= 30:
            break
    if not items:
        first_line = next((line.strip() for line in markdown.splitlines() if line.strip()), "Trend result")
        items.append(
            {
                "title": first_line[:180],
                "url": source_url,
                "price": None,
                "thumbnail": "",
                "likes": 0,
                "downloads": 0,
                "prints_count": 0,
                "designer": "",
                "category": "",
            }
        )
    return items


@app.get("/health")
@app.get("/health/live")
async def health() -> dict[str, str]:
    return {"status": "alive", "service": APP_NAME, "version": "0.1.0"}


@app.post("/v2/scrape", dependencies=[Depends(_check_auth)])
async def scrape(payload: ScrapeRequest) -> dict[str, Any]:
    url = _safe_url(str(payload.url))
    timeout = min(max(payload.timeout_ms / 1000, 1), REQUEST_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content[:MAX_RESPONSE_BYTES]
    except httpx.HTTPError as exc:
        return {"success": False, "error": str(exc)}

    markdown, links = _text_from_html(content.decode(response.encoding or "utf-8", errors="replace"))
    data: dict[str, Any] = {"markdown": markdown, "metadata": {"sourceURL": url}}
    if "extract" in payload.formats:
        data["extract"] = _extract_items(markdown, links, url)
    return {"success": True, "data": data}


@app.post("/v2/search", dependencies=[Depends(_check_auth)])
async def search(payload: SearchRequest) -> dict[str, Any]:
    return {
        "success": True,
        "data": [],
        "warning": "Search is intentionally disabled in the DFPos internal adapter; use configured target URLs.",
        "query": payload.query,
        "limit": payload.limit,
    }
