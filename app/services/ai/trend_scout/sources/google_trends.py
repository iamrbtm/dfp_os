from __future__ import annotations

import os
from statistics import mean
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult, build_json_api_headers, request_with_retry

SERPAPI_URL = "https://serpapi.com/search.json"

SEED_QUERIES = [
    "personalized keychain",
    "teacher appreciation gift",
    "back to school gift",
    "3d printed fidget toy",
    "desk organizer",
    "business card holder",
    "qr code sign",
    "dice tower",
    "board game organizer",
    "custom name sign",
    "stocking stuffer",
    "tennessee gift",
    "clarksville tn gift",
]


def _parse_serpapi_interest(data: dict[str, Any], query: str) -> ScoutResult:
    result = ScoutResult(source="google_trends", keyword_or_category=query)
    timeline = data.get("interest_over_time", {}).get("timeline_data", []) or []
    values: list[int] = []
    for point in timeline:
        value = 0
        point_values = point.get("values") or []
        if point_values:
            extracted = point_values[0].get("extracted_value")
            value = int(extracted or 0)
        values.append(value)

    related_queries = []
    for block in data.get("related_queries", {}) or []:
        if isinstance(block, dict):
            related_queries.extend(block.get("query", []) or [])

    result.metadata = {
        "provider": "serpapi",
        "points": len(values),
        "latest_interest": values[-1] if values else 0,
        "average_interest": round(mean(values), 2) if values else 0,
        "peak_interest": max(values) if values else 0,
        "related_queries": related_queries[:20],
    }
    if values:
        result.items.append(
            {
                "title": query,
                "keyword": query,
                "interest": values[-1],
                "average_interest": result.metadata["average_interest"],
                "peak_interest": result.metadata["peak_interest"],
                "source": "serpapi_google_trends",
            }
        )
    return result


def _fetch_with_serpapi(session: requests.Session, limiter: Any, api_key: str) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    for query in SEED_QUERIES:
        limiter.wait()
        try:
            resp = request_with_retry(
                session, "GET",
                SERPAPI_URL,
                params={
                    "engine": "google_trends",
                    "q": query,
                    "geo": "US",
                    "date": "today 12-m",
                    "api_key": api_key,
                },
                headers=build_json_api_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                results.append(_parse_serpapi_interest(resp.json(), query))
            else:
                results.append(
                    ScoutResult(
                        source="google_trends",
                        keyword_or_category=query,
                        errors=[f"HTTP {resp.status_code}"],
                    )
                )
        except (requests.RequestException, ValueError) as exc:
            results.append(
                ScoutResult(source="google_trends", keyword_or_category=query, errors=[str(exc)])
            )
    return results


def _fetch_with_pytrends(limiter: Any) -> list[ScoutResult]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return [
            ScoutResult(
                source="google_trends",
                keyword_or_category="not_configured",
                errors=[
                    "Set SERPAPI_API_KEY or install/configure pytrends to enable Google Trends data."
                ],
                metadata={"provider": "none"},
            )
        ]

    pytrends = TrendReq(hl="en-US", tz=360)
    results: list[ScoutResult] = []
    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="google_trends", keyword_or_category=query)
        try:
            pytrends.build_payload([query], timeframe="today 12-m", geo="US")
            frame = pytrends.interest_over_time()
            values = []
            if not frame.empty and query in frame:
                for date, value in frame[query].items():
                    int_value = int(value)
                    values.append(int_value)
            result.metadata = {
                "provider": "pytrends",
                "points": len(values),
                "latest_interest": values[-1] if values else 0,
                "average_interest": round(mean(values), 2) if values else 0,
                "peak_interest": max(values) if values else 0,
            }
            if values:
                result.items.append(
                    {
                        "title": query,
                        "keyword": query,
                        "interest": values[-1],
                        "average_interest": result.metadata["average_interest"],
                        "peak_interest": result.metadata["peak_interest"],
                        "source": "pytrends",
                    }
                )
        except Exception as exc:
            result.errors.append(str(exc))
        results.append(result)
    return results


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    serpapi_key = os.getenv("SERPAPI_API_KEY", "")
    if serpapi_key:
        return _fetch_with_serpapi(session, limiter, serpapi_key)
    return _fetch_with_pytrends(limiter)
