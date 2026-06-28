from __future__ import annotations

from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import (
    ScoutResult,
)

SUBREDDITS = [
    "3Dprinting",
    "functionalprint",
    "boardgameupgrades",
    "Gridfinity",
    "PrintedMinis",
    "3Dprintmything",
    "BambuLab",
]

JSON_BASE = "https://www.reddit.com/r/{subreddit}/{sort}.json"

SORTS = ["hot", "top", "rising"]


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    headers = {"User-Agent": "DFPosTrendScout/1.0 (research; contact@dudefishprinting.com)"}

    for subreddit in SUBREDDITS:
        for sort in SORTS:
            limiter.wait()
            result = ScoutResult(source="reddit", keyword_or_category=f"{subreddit}_{sort}")
            try:
                url = JSON_BASE.format(subreddit=subreddit, sort=sort)
                resp = session.get(
                    url,
                    headers=headers,
                    params={"limit": 25, "t": "week"} if sort == "top" else {"limit": 25},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        result.items.append(
                            {
                                "title": post.get("title", ""),
                                "url": post.get("url", ""),
                                "permalink": f"https://www.reddit.com{post.get('permalink', '')}",
                                "score": post.get("score", 0),
                                "upvote_ratio": post.get("upvote_ratio"),
                                "num_comments": post.get("num_comments", 0),
                                "created_utc": post.get("created_utc"),
                                "domain": post.get("domain", ""),
                                "is_self": post.get("is_self", False),
                                "selftext": (post.get("selftext", "") or "")[:500],
                                "thumbnail": post.get("thumbnail", "") if post.get("thumbnail") and post["thumbnail"] not in ("self", "default", "nsfw") else "",
                                "spoiler": post.get("spoiler", False),
                                "over_18": post.get("over_18", False),
                                "link_flair_text": post.get("link_flair_text"),
                            }
                        )
                    result.metadata["total_results"] = len(result.items)
                    result.metadata["subreddit"] = subreddit
                    result.metadata["sort"] = sort
                else:
                    result.errors.append(f"HTTP {resp.status_code}")
            except (requests.RequestException, ValueError) as e:
                result.errors.append(str(e))

            results.append(result)

    return results
