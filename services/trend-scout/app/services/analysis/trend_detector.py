"""Trend detector for the Trend Scout microservice.

Computes velocity (recent change in item count) and momentum (week-over-week
trend direction) from TrendSnapshot rows. Top opportunities are then ranked
by a 7-dimension scoring formula whose weights come from the weights module.

This Phase 3 implementation is intentionally compact and well-tested. The
heavier NLP/DBSCAN clustering that the monolith's 1,131-line trend_detector.py
performed is split into ``new_category_discovery`` and the orchestration
in ``orchestrator.py``. Behavior parity is preserved at the data-model level.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TrendSnapshot
from app.services.weights import (
    DEFAULT_BUYER_SOURCE_WEIGHTS,
    DEFAULT_METRIC_WEIGHTS,
    DEFAULT_SOURCE_WEIGHTS,
)

logger = logging.getLogger(__name__)

LOCAL_KEYWORDS = {"clarksville", "tennessee", "fort campbell", "military family"}
RISK_KEYWORDS = {"weapon", "gun", "firearm", "nintendo", "disney", "marvel", "star wars"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except TypeError, ValueError:
        return default


def _keyword_signal(keyword: str, lower: str) -> tuple[float, float, str]:
    """Return (local_relevance, license_risk_score, license_risk_label)."""
    local = 0.0
    risk = 0.0
    for term in LOCAL_KEYWORDS:
        if term in lower:
            local = max(local, 0.6)
    for term in RISK_KEYWORDS:
        if term in lower:
            risk = max(risk, 0.8)
    label = "high" if risk > 0.5 else "low" if risk < 0.1 else "unknown"
    return local, risk, label


def _metric_value(item: dict[str, Any], metric_weights: dict[str, float]) -> tuple[float, str]:
    best_key = None
    best_weight = 0.0
    total = 0.0
    for metric, weight in metric_weights.items():
        if metric in item:
            value = _safe_float(item.get(metric), 0.0)
            if value > 0 and weight > best_weight:
                best_key = metric
                best_weight = weight
            total += value * weight
    return total, best_key or "items"


def score_breakdown_for_opportunity(
    opportunity: dict[str, Any],
    weights: dict[str, Any],
) -> dict[str, float]:
    """Compute the named weight contributions for a single opportunity."""
    score_weights = weights.get("score_weights", {})
    return {
        "purchase_intent": opportunity.get("purchase_intent", 0.0) * score_weights.get("purchase_intent", 1.0),
        "trend_velocity": opportunity.get("velocity", 0.0) * score_weights.get("trend_velocity", 1.0),
        "price_resilience": opportunity.get("price_resilience", 0.0) * score_weights.get("price_resilience", 1.0),
        "low_saturation": opportunity.get("low_saturation", 0.0) * score_weights.get("low_saturation", 1.0),
        "local_fit": opportunity.get("local_relevance", 0.0) * score_weights.get("local_fit", 1.0),
        "production_fit": opportunity.get("production_fit", 0.0) * score_weights.get("production_fit", 1.0),
        "license_risk": opportunity.get("license_risk", 0.0) * score_weights.get("license_risk", 1.0),
    }


def recommended_action_for_score(score: float) -> str:
    if score >= 70:
        return "print_now"
    if score >= 40:
        return "watch"
    return "skip"


def _find_matched_local_terms(keyword: str) -> list[str]:
    return sorted(term for term in LOCAL_KEYWORDS if term in keyword.lower())


def _find_matched_risk_terms(keyword: str) -> list[str]:
    return sorted(term for term in RISK_KEYWORDS if term in keyword.lower())


async def compute_velocity_and_momentum(session: AsyncSession) -> dict[str, Any]:
    """Aggregate TrendSnapshot rows into per-(source, keyword) velocity.

    Velocity = item_count this week vs last week (fractional).
    Momentum = direction label (up / down / flat) per (source, keyword).
    """
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    two_weeks = now - timedelta(days=14)

    stmt = select(TrendSnapshot).where(TrendSnapshot.scraped_at >= two_weeks).order_by(TrendSnapshot.scraped_at.desc())
    snapshots = list((await session.execute(stmt)).scalars().all())

    by_keyword: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: {"recent": [], "prior": []})
    for snap in snapshots:
        if not snap.keyword_or_category:
            continue
        bucket = by_keyword[(snap.source, snap.keyword_or_category)]
        target = bucket["recent"] if snap.scraped_at >= week_start else bucket["prior"]
        target.append(int(snap.item_count or 0))

    velocity_map: dict[str, dict[str, float]] = defaultdict(dict)
    momentum_map: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    cross_source: dict[str, int] = defaultdict(int)
    for (source, keyword), buckets in by_keyword.items():
        recent_avg = sum(buckets["recent"]) / len(buckets["recent"]) if buckets["recent"] else 0.0
        prior_avg = sum(buckets["prior"]) / len(buckets["prior"]) if buckets["prior"] else 0.0
        delta = recent_avg - prior_avg
        if prior_avg > 0:
            velocity = delta / prior_avg
        elif recent_avg > 0:
            velocity = 1.0
        else:
            velocity = 0.0

        if velocity > 0.10:
            direction = "up"
        elif velocity < -0.10:
            direction = "down"
        else:
            direction = "flat"

        velocity_map[source][keyword] = round(velocity, 4)
        momentum_map[source][keyword] = {
            "direction": direction,
            "recent_avg": recent_avg,
            "prior_avg": prior_avg,
        }
        if direction == "up":
            cross_source[keyword] += 1

    return {
        "velocity": {k: dict(v) for k, v in velocity_map.items()},
        "momentum": {k: dict(v) for k, v in momentum_map.items()},
        "cross_source": dict(cross_source),
        "metadata": {
            "snapshots_processed": len(snapshots),
            "keyword_pairs": len(by_keyword),
            "generated_at": now.isoformat(),
        },
    }


def compute_growing_and_declining(
    velocity: dict[str, Any],
    clusters: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Derive human-readable growing/declining category names.

    Combines velocity signals with cluster top phrases.
    """
    growing: list[str] = []
    declining: list[str] = []
    cross_source = velocity.get("cross_source", {})
    sorted_growing = sorted(cross_source.items(), key=lambda item: -item[1])
    growing.extend(name for name, _ in sorted_growing[:15])
    for cluster in clusters.get("clusters", [])[:5]:
        for phrase in cluster.get("top_phrases", [])[:3]:
            if phrase and phrase not in growing:
                growing.append(phrase)

    momentum = velocity.get("momentum", {})
    for source_mom in momentum.values():
        for keyword, info in source_mom.items():
            if info.get("direction") == "down" and keyword not in declining:
                declining.append(keyword)
            if len(declining) >= 15:
                break
    return growing[:20], declining[:20]


async def compute_top_opportunities(
    session: AsyncSession,
    weights: dict[str, Any] | None = None,
    business_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Aggregate per-(source, keyword) opportunities and rank them.

    The output mirrors the monolith's opportunity shape so the admin UI proxy
    in Phase 6 can render it without changes.
    """
    if weights is None:
        weights = {
            "score_weights": {},
            "source_weights": dict(DEFAULT_SOURCE_WEIGHTS),
            "buyer_source_weights": dict(DEFAULT_BUYER_SOURCE_WEIGHTS),
            "metric_weights": dict(DEFAULT_METRIC_WEIGHTS),
        }

    source_weights = weights.get("source_weights", dict(DEFAULT_SOURCE_WEIGHTS))
    buyer_source_weights = weights.get("buyer_source_weights", dict(DEFAULT_BUYER_SOURCE_WEIGHTS))
    metric_weights = weights.get("metric_weights", dict(DEFAULT_METRIC_WEIGHTS))

    stmt = (
        select(TrendSnapshot)
        .where(TrendSnapshot.scraped_at >= datetime.now(timezone.utc) - timedelta(days=14))
        .order_by(TrendSnapshot.scraped_at.desc())
    )
    snapshots = list((await session.execute(stmt)).scalars().all())

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for snap in snapshots:
        if not snap.keyword_or_category:
            continue
        key = (snap.source, snap.keyword_or_category)
        meta = snap.raw_metadata or {}
        bucket = grouped.setdefault(
            key,
            {
                "source": snap.source,
                "keyword": snap.keyword_or_category,
                "items": [],
                "purchase_intent": 0.0,
                "first_seen": snap.scraped_at,
                "title": "",
            },
        )
        items = meta.get("items") if isinstance(meta, dict) else None
        if isinstance(items, list):
            bucket["items"].extend(items)
        if snap.scraped_at and snap.scraped_at < bucket["first_seen"]:
            bucket["first_seen"] = snap.scraped_at
        for item in items or []:
            if isinstance(item, dict):
                if not bucket["title"] and item.get("title"):
                    bucket["title"] = item["title"]
                purchase_score = _safe_float(item.get("purchase_score"))
                if purchase_score > 0:
                    bucket["purchase_intent"] = max(bucket["purchase_intent"], purchase_score)

    opportunities: list[dict[str, Any]] = []
    for (source, keyword), bucket in grouped.items():
        items = [i for i in bucket["items"] if isinstance(i, dict)]
        if not items:
            continue
        item_count = len(items)
        aggregate_metric, _metric_key = _metric_value(
            {k: v for item in items for k, v in item.items() if isinstance(v, (int, float))},
            metric_weights,
        )
        local, risk, license_risk_label = _keyword_signal(keyword, keyword.lower())
        source_weight = source_weights.get(source, 1.0)
        buyer_weight = buyer_source_weights.get(source, 1.0)

        velocity = 0.0
        momentum = 0.0
        if bucket["first_seen"]:
            age_days = max(
                1.0,
                (datetime.now(timezone.utc) - bucket["first_seen"]).total_seconds() / 86400.0,
            )
            velocity = min(1.0, item_count / (age_days * 5.0))
            momentum = velocity

        price_resilience = min(1.0, item_count / 25.0)
        low_saturation = max(0.0, 1.0 - min(1.0, item_count / 100.0))
        production_fit = 0.5
        purchase_intent = min(
            1.0,
            (bucket["purchase_intent"] / 100.0) + 0.2 * buyer_weight + 0.1 * source_weight,
        )

        score_breakdown = {
            "purchase_intent": purchase_intent,
            "velocity": velocity,
            "price_resilience": price_resilience,
            "low_saturation": low_saturation,
            "local_relevance": local,
            "production_fit": production_fit,
            "license_risk": risk,
        }
        weights_bd = score_breakdown_for_opportunity(
            {
                "purchase_intent": purchase_intent,
                "velocity": velocity,
                "price_resilience": price_resilience,
                "local_relevance": local,
                "production_fit": production_fit,
                "license_risk": risk,
            },
            {"score_weights": weights.get("score_weights", {})},
        )
        weighted_score = sum(weights_bd.values()) - risk * source_weight
        score_0_100 = max(0.0, min(100.0, 50.0 + weighted_score * 50.0))

        opportunities.append(
            {
                "keyword": keyword,
                "source": source,
                "title": bucket["title"] or keyword,
                "score": round(score_0_100, 2),
                "score_breakdown": {
                    "raw": score_breakdown,
                    "weighted": weights_bd,
                    "source_weight": source_weight,
                    "buyer_weight": buyer_weight,
                    "aggregate_metric": aggregate_metric,
                    "item_count": item_count,
                },
                "velocity": round(velocity, 4),
                "momentum": round(momentum, 4),
                "purchase_intent": round(purchase_intent, 4),
                "license_risk": license_risk_label,
                "local_relevance": round(local, 4),
                "recommended_action": recommended_action_for_score(score_0_100),
                "matched_local_terms": _find_matched_local_terms(keyword),
                "matched_risk_terms": _find_matched_risk_terms(keyword),
            }
        )

    opportunities.sort(key=lambda item: -item["score"])
    return opportunities[:limit]
