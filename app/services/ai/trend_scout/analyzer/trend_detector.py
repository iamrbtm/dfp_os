from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.trend import TrendSnapshot


def _week_start(dt: datetime) -> datetime:
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def compute_velocity_and_momentum(
    db_session: Session, lookback_weeks: int = 8
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)

    rows = (
        db_session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at >= cutoff)
        .all()
    )

    weekly_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    source_keywords: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        week_label = _week_start(row.scraped_at).isoformat()
        key = (row.source, row.keyword_or_category, week_label)
        weekly_counts[key] += len(row.raw_metadata.get("items", [])) if row.raw_metadata else 1
        source_keywords[row.source].add(row.keyword_or_category)

    velocity: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (source, keyword, week), count in sorted(weekly_counts.items()):
        velocity[source][keyword].append({"week": week, "count": count})

    trends: dict[str, Any] = {
        "velocity": velocity,
        "momentum": {},
        "cross_source": {},
        "metadata": {"lookback_weeks": lookback_weeks, "total_rows": len(rows)},
    }

    for source, keywords in velocity.items():
        for keyword, weeks in keywords.items():
            if len(weeks) >= 2:
                first_half = sum(w["count"] for w in weeks[: len(weeks) // 2])
                second_half = sum(w["count"] for w in weeks[len(weeks) // 2 :])
                delta = second_half - first_half
                trends["momentum"].setdefault(source, {})[keyword] = {
                    "first_half_total": first_half,
                    "second_half_total": second_half,
                    "delta": delta,
                    "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
                }

    keyword_sources: dict[str, set[str]] = defaultdict(set)
    for source, keywords in source_keywords.items():
        for kw in keywords:
            base = kw.split("_")[-1] if "_" in kw else kw
            keyword_sources[base].add(source)

    cross_source = {
        kw: sorted(sources)
        for kw, sources in keyword_sources.items()
        if len(sources) > 1
    }
    trends["cross_source"] = {
        "appearing_across_multiple_sources": cross_source,
        "total_cross_source_keywords": len(cross_source),
    }

    return trends


def compute_top_opportunities(
    db_session: Session, lookback_weeks: int = 4
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)

    rows = (
        db_session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at >= cutoff)
        .all()
    )

    keyword_score: dict[str, float] = defaultdict(float)
    for row in rows:
        items = (row.raw_metadata or {}).get("items", [])
        base_keyword = row.keyword_or_category.split("_")[-1]
        score = len(items) * (1 + ("category" in row.keyword_or_category))
        keyword_score[base_keyword] += score

    sorted_keywords = sorted(keyword_score.items(), key=lambda x: -x[1])
    return [
        {"keyword": kw, "score": round(score, 1), "rank": i + 1}
        for i, (kw, score) in enumerate(sorted_keywords[:20])
    ]
