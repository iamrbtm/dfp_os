from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult, build_json_api_headers, request_with_retry

RESEARCH_VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"

SEED_QUERIES = [
    "personalized gift",
    "teacher gift",
    "back to school gift",
    "fidget toy",
    "desk organizer",
    "small business display",
    "vendor booth",
    "dice tower",
    "board game organizer",
    "custom keychain",
    "stocking stuffer",
    "3d printed gift",
]


def _date_window() -> tuple[str, str]:
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=29)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _video_to_item(video: dict[str, Any], query: str) -> dict[str, Any]:
    return {
        "title": video.get("video_description") or query,
        "url": f"https://www.tiktok.com/@/video/{video.get('id', '')}" if video.get("id") else "",
        "published": video.get("create_time", ""),
        "region_code": video.get("region_code", ""),
        "views": video.get("view_count", 0),
        "likes": video.get("like_count", 0),
        "comments": video.get("comment_count", 0),
        "shares": video.get("share_count", 0),
        "hashtags": video.get("hashtag_names", []),
        "query": query,
    }


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    access_token = os.getenv("TIKTOK_RESEARCH_ACCESS_TOKEN", "")
    if not access_token:
        return [
            ScoutResult(
                source="tiktok",
                keyword_or_category="not_configured",
                errors=[
                    "Set TIKTOK_RESEARCH_ACCESS_TOKEN with approved Research API access to enable TikTok trend data."
                ],
            )
        ]

    start_date, end_date = _date_window()
    results: list[ScoutResult] = []
    fields = ",".join(
        [
            "id",
            "video_description",
            "create_time",
            "region_code",
            "like_count",
            "comment_count",
            "share_count",
            "view_count",
            "hashtag_names",
        ]
    )
    headers = build_json_api_headers()
    headers["Authorization"] = f"Bearer {access_token}"

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="tiktok", keyword_or_category=query)
        body = {
            "query": {
                "and": [
                    {
                        "operation": "IN",
                        "field_name": "keyword",
                        "field_values": [query],
                    }
                ]
            },
            "start_date": start_date,
            "end_date": end_date,
            "max_count": 20,
        }
        try:
            resp = request_with_retry(
                session, "POST",
                RESEARCH_VIDEO_QUERY_URL,
                params={"fields": fields},
                json=body,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                videos = data.get("videos", []) or []
                result.items = [_video_to_item(video, query) for video in videos]
                result.metadata = {
                    "total_results": len(result.items),
                    "start_date": start_date,
                    "end_date": end_date,
                    "has_more": data.get("has_more", False),
                    "cursor": data.get("cursor"),
                }
            elif resp.status_code in {401, 403}:
                result.errors.append(
                    f"HTTP {resp.status_code} - TikTok Research API token is missing required access."
                )
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except (requests.RequestException, ValueError) as exc:
            result.errors.append(str(exc))
        results.append(result)

    return results
