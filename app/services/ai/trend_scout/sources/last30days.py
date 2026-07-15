from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.services.ai.trend_scout.sources._base import ScoutResult

logger = logging.getLogger(__name__)

DEFAULT_RAW_FILE = os.path.expanduser(
    "~/Documents/Last30Days/3d-printing-ideas-what-people-buy-sell-raw-v3.md"
)

CLUSTER_HEADING_RE = re.compile(
    r"^###\s+(\d+)\.\s+(.+?)\s+\(score\s+(\d+),\s*(\d+)\s+item",
    re.MULTILINE,
)

ITEM_ENTRY_RE = re.compile(r"^\d+\.\s+\[(\w+)\]\s+(.+?)$", re.MULTILINE)

URL_LINE_RE = re.compile(r"^\s*URL:\s*(https?://\S+)\s*$", re.MULTILINE)

COMMENT_RE = re.compile(
    r"^\s*-\s*@([\w.-]+)\s*\((\d+)\s*likes?\):\s*(.+)$", re.MULTILINE
)

META_BRACKET_RE = re.compile(r"\[([^\]]*?(?:\d[\d,]*[kKmMbB]?views?[^\]]*))\]", re.IGNORECASE)

SCORE_LINE_RE = re.compile(r"\|\s*score:(\d+)")

HIGHLIGHTS_MARKER_RE = re.compile(r"^\s*-\s*Highlights\b", re.MULTILINE)


SOURCE_LABEL_MAP: dict[str, str] = {
    "youtube": "youtube",
    "reddit": "reddit",
    "tiktok": "tiktok",
    "instagram": "instagram",
    "hacker news": "hackernews",
    "hackernews": "hackernews",
    "github": "github",
}


def _normalise_source_label(label: str) -> str:
    return SOURCE_LABEL_MAP.get(label.strip().lower(), label.strip().lower())


def _parse_bracket_metrics(text: str) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for m in META_BRACKET_RE.finditer(text):
        content = m.group(1)
        for part in re.split(r",\s*", content):
            part = part.strip().lower()
            m2 = re.match(r"([\d,]+(?:\.\d+)?)\s*(views|likes|cmt|comments|shares)?", part)
            if not m2:
                continue
            try:
                val = int(m2.group(1).replace(",", ""))
            except ValueError:
                val = 0
            suffix = m2.group(2) or ""
            if suffix in ("cmt", "comments"):
                metrics["comments"] = metrics.get("comments", 0) + val
            elif suffix == "likes":
                metrics["likes"] = metrics.get("likes", 0) + val
            elif suffix == "views":
                metrics["views"] = metrics.get("views", 0) + val
            elif suffix == "shares":
                metrics["shares"] = metrics.get("shares", 0) + val
    return metrics


def _parse_item_block(text: str) -> dict[str, Any]:
    item: dict[str, Any] = {}

    url_m = URL_LINE_RE.search(text)
    if url_m:
        item["url"] = url_m.group(1)

    bracket_metrics = _parse_bracket_metrics(text)
    if bracket_metrics:
        item.update(bracket_metrics)

    score_m = SCORE_LINE_RE.search(text)
    if score_m:
        try:
            item["score"] = int(score_m.group(1))
        except ValueError:
            pass

    highlights_end = HIGHLIGHTS_MARKER_RE.search(text)
    comment_region = text[: highlights_end.start()] if highlights_end else text
    comments = []
    for cm in COMMENT_RE.finditer(comment_region):
        comments.append(
            {
                "user": cm.group(1),
                "likes": int(cm.group(2)),
                "text": cm.group(3).strip(),
            }
        )
    if comments:
        item["top_comments"] = comments

    return item


def _extract_items_from_cluster(cluster_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    matches = list(ITEM_ENTRY_RE.finditer(cluster_text))
    for i, m in enumerate(matches):
        platform = m.group(1).lower()
        title = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cluster_text)
        block = cluster_text[start:end]

        item = _parse_item_block(block)
        item["title"] = title
        item["platform"] = platform
        items.append(item)
    return items


def _clean_keyword(title: str) -> str:
    kw = re.sub(r"[^a-zA-Z0-9 ]+", " ", title).strip().lower()
    kw = re.sub(r"\s+", "_", kw)
    return kw[:100]


def fetch_trending(session=None, limiter=None) -> list[ScoutResult]:
    raw_file = os.getenv("LAST30DAYS_RAW_FILE", DEFAULT_RAW_FILE)

    if not os.path.isfile(raw_file):
        return [
            ScoutResult(
                source="last30days",
                keyword_or_category="not_configured",
                errors=[
                    f"LAST30DAYS_RAW_FILE not found: {raw_file}. "
                    "Run the /last30days skill to generate a raw research file first."
                ],
            )
        ]

    try:
        with open(raw_file, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, PermissionError) as exc:
        return [
            ScoutResult(
                source="last30days",
                keyword_or_category="pipeline_error",
                errors=[f"Cannot read {raw_file}: {exc}"],
            )
        ]

    clusters: list[dict[str, Any]] = []
    for m in CLUSTER_HEADING_RE.finditer(content):
        cluster = {
            "num": int(m.group(1)),
            "title": m.group(2).strip(),
            "score": int(m.group(3)),
            "item_count": int(m.group(4)),
            "start": m.end(),
        }
        clusters.append(cluster)

    if not clusters:
        return [
            ScoutResult(
                source="last30days",
                keyword_or_category="pipeline_error",
                errors=[
                    f"No evidence clusters found in {raw_file}. "
                    "The raw file format may have changed."
                ],
            )
        ]

    for i, cluster in enumerate(clusters):
        if i + 1 < len(clusters):
            cluster["text"] = content[cluster["start"] : clusters[i + 1]["start"]]
        else:
            cluster["text"] = content[cluster["start"] :]

    results: list[ScoutResult] = []
    aggregate_items_global: list[dict[str, Any]] = []

    for cluster in clusters:
        items = _extract_items_from_cluster(cluster["text"])
        if not items:
            continue

        keyword = _clean_keyword(cluster["title"])
        if not keyword:
            keyword = f"cluster_{cluster['num']}"

        result = ScoutResult(
            source="last30days",
            keyword_or_category=keyword,
            items=items,
            metadata={
                "cluster_num": cluster["num"],
                "cluster_title": cluster["title"],
                "cluster_score": cluster["score"],
                "item_count": len(items),
            },
        )
        results.append(result)
        aggregate_items_global.extend(items)

    if not results:
        return [
            ScoutResult(
                source="last30days",
                keyword_or_category="pipeline_error",
                errors=[
                    "Clusters found but no items could be parsed. "
                    "Check the raw file format."
                ],
            )
        ]

    source_platforms = set()
    for item in aggregate_items_global:
        p = item.get("platform")
        if p:
            source_platforms.add(p)

    total_views = sum(item.get("views", 0) for item in aggregate_items_global)
    total_likes = sum(item.get("likes", 0) for item in aggregate_items_global)

    aggregate = ScoutResult(
        source="last30days",
        keyword_or_category="synthesis_aggregate",
        metadata={
            "cluster_count": len(results),
            "platforms_found": sorted(source_platforms),
            "total_items": len(aggregate_items_global),
            "total_views": total_views,
            "total_likes": total_likes,
        },
    )
    results.append(aggregate)

    return results
