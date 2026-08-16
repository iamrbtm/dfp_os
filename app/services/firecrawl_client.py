from __future__ import annotations

import os

import httpx


class FirecrawlClientError(RuntimeError):
    """Raised when a Firecrawl scrape fails or returns no usable content."""


class FirecrawlClient:
    """Thin wrapper around the Firecrawl v2 /scrape endpoint.

    Used by the market-catalog web importers to fetch page content (markdown)
    from external sites that may need a real browser/JSRender. Mirrors the
    contract used by the trend-scout service but lives inside the app so the
    importers do not depend on the separate microservice package.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("FIRECRAWL_API_URL", "http://localhost:9500")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("FIRECRAWL_TIMEOUT_SECONDS", "30"))
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def scrape(
        self,
        url: str,
        *,
        formats: list[str] | None = None,
        only_main_content: bool = True,
        timeout_ms: int = 30000,
    ) -> dict:
        """Return the raw Firecrawl JSON response for a single URL."""
        body: dict = {
            "url": url,
            "formats": formats or ["markdown"],
            "onlyMainContent": only_main_content,
            "timeout": timeout_ms,
        }
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as client:
                response = client.post("/v2/scrape", json=body)
        except httpx.HTTPError as exc:
            raise FirecrawlClientError(f"Firecrawl request failed for {url}: {exc}") from exc

        if response.status_code >= 400:
            raise FirecrawlClientError(
                f"Firecrawl HTTP {response.status_code} for {url}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise FirecrawlClientError(f"Firecrawl returned invalid JSON for {url}") from exc

    def scrape_markdown(self, url: str, **kwargs: object) -> str:
        """Return page markdown for ``url`` or raise if none is available."""
        data = self.scrape(url, **kwargs)
        markdown = (data.get("data") or {}).get("markdown")
        if not markdown and data.get("markdown"):
            markdown = data["markdown"]
        if not markdown:
            raise FirecrawlClientError(f"Firecrawl returned no markdown for {url}")
        return markdown
