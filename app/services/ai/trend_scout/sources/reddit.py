from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Any

import feedparser

from app.services.ai.trend_scout.sources._base import ScoutResult

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "3Dprinting",
    "functionalprint",
    "Gridfinity",
    "BambuLab",
    "3Dprintmything",
    "3Dprinting_help",
    "FDMPrinted",
    "AdditiveManufacturing",
    "3Dprintedart",
    "resinprinting",
    "3Dprintingdeals",
    "fixmyprint",
]

FEED_TYPES = [
    ("hot", "https://www.reddit.com/r/{subreddit}/.rss"),
    ("new", "https://www.reddit.com/r/{subreddit}/new/.rss"),
]

REDDIT_REQUEST_INTERVAL = 15.0

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15"


def _fetch_feed_via_curl(url: str, timeout: int = 30) -> tuple[int, bytes]:
    """Use curl to bypass TLS fingerprint blocking.
    Returns (http_status_code, body_bytes)."""
    result = subprocess.run(
        [
            "curl",
            "-s",
            "-L",
            "-w",
            "%{http_code}",
            "--max-time",
            str(timeout),
            "-H",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
            "-H",
            "Accept: application/rss+xml, application/xml, text/xml, */*",
            url,
        ],
        capture_output=True,
        timeout=timeout + 5,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"curl failed (exit {result.returncode}): {stderr}")
    stdout = result.stdout
    if len(stdout) < 3:
        return (0, stdout)
    status_bytes = stdout[-3:]
    body = stdout[:-3] if len(stdout) > 3 else b""
    try:
        status = int(status_bytes)
    except ValueError:
        return (0, stdout)
    return (status, body)


def extract_entry_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def fetch_trending(session: Any, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    last_fetch: float = 0.0

    for subreddit in SUBREDDITS:
        seen_urls: set[str] = set()

        for feed_label, feed_url_template in FEED_TYPES:
            elapsed = time.monotonic() - last_fetch
            if elapsed < REDDIT_REQUEST_INTERVAL:
                time.sleep(REDDIT_REQUEST_INTERVAL - elapsed)

            result = ScoutResult(
                source="reddit",
                keyword_or_category=f"{subreddit}/{feed_label}",
            )

            try:
                url = feed_url_template.format(subreddit=subreddit)
                status, content = _fetch_feed_via_curl(url)
                last_fetch = time.monotonic()

                if status != 200:
                    result.errors.append(f"HTTP {status}")
                else:
                    feed = feedparser.parse(content)

                    for entry in feed.entries:
                        link = entry.get("link", "")
                        if not link or link in seen_urls:
                            continue
                        seen_urls.add(link)

                        thumbnail = ""
                        media = entry.get("media_thumbnail", [])
                        if media:
                            thumbnail = media[0].get("url", "")

                        author = (entry.get("author") or "").lstrip("/u/")

                        summary_html = entry.get("summary", "")
                        selftext = extract_entry_text(summary_html)

                        result.items.append(
                            {
                                "title": entry.get("title", ""),
                                "url": link,
                                "feed": feed_label,
                                "author": author,
                                "published": entry.get("published", ""),
                                "selftext": selftext,
                                "thumbnail": thumbnail,
                            }
                        )

                    result.metadata["total_results"] = len(result.items)
                    result.metadata["subreddit"] = subreddit
                    result.metadata["feed_type"] = feed_label
                    result.metadata["feed_url"] = url

            except (RuntimeError, OSError) as e:
                result.errors.append(str(e))

            results.append(result)

    return results
