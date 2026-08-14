"""Scoring weights module for the Trend Scout microservice.

Replaces the Flask-app ``app.services.trend_scout_weights`` module. Weights live
in the ``trend_weights`` table (added in Phase 1 migration 0001_initial). The
public surface mirrors the original module so the analyzer (Phase 3) and
backtest (Phase 3) can drop in unchanged.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TrendWeight

DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "purchase_intent": 0.30,
    "trend_velocity": 0.18,
    "price_resilience": 0.14,
    "low_saturation": 0.12,
    "local_fit": 0.10,
    "production_fit": 0.12,
    "license_risk": 0.16,
}


DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "internal_demand": 1.6,
    "google_trends": 1.3,
    "etsy": 1.25,
    "last30days": 1.2,
    "makerworld": 1.15,
    "tiktok": 1.15,
    "printables": 1.1,
    "myminifactory": 1.0,
    "reddit": 0.95,
    "pinterest": 0.9,
    "bgg": 0.8,
    # Firecrawl source weights (Phase 8).
    "firecrawl_cults3d": 1.0,
    "firecrawl_thangs": 0.9,
    "firecrawl_stlfinder": 0.8,
    "firecrawl_cgtrader": 0.9,
    "firecrawl_mmf": 1.0,
    "firecrawl_general": 0.5,
    # Throttled target — lower because it is best-effort.
    "firecrawl_etsy": 0.4,
}


DEFAULT_BUYER_SOURCE_WEIGHTS: dict[str, float] = {
    "internal_demand": 1.0,
    "etsy": 0.65,
    "google_trends": 0.35,
    "tiktok": 0.25,
    "last30days": 0.20,
    "reddit": 0.15,
    "pinterest": 0.15,
    "firecrawl_etsy": 0.25,
    "firecrawl_cults3d": 0.30,
    "firecrawl_thangs": 0.25,
    "firecrawl_stlfinder": 0.20,
    "firecrawl_cgtrader": 0.20,
}


DEFAULT_METRIC_WEIGHTS: dict[str, float] = {
    "downloads": 0.22,
    "download_count": 0.22,
    "prints_count": 0.2,
    "print_count": 0.2,
    "makes": 0.2,
    "likes": 0.15,
    "num_favorers": 0.15,
    "favorites": 0.15,
    "saves": 0.14,
    "views": 0.08,
    "visits": 0.08,
    "impressions": 0.05,
    "comments": 0.08,
    "shares": 0.1,
    "interest": 0.05,
    "event_count": 0.35,
    "quantity": 0.45,
    "purchase_score": 0.6,
    "revenue": 0.08,
}


DEFAULT_SOURCE_ENABLED: dict[str, bool] = {name: True for name in DEFAULT_SOURCE_WEIGHTS}


PREFIX_SCORE = "trend_weight."
PREFIX_SOURCE = "trend_source."
PREFIX_BUYER = "trend_buyer."
PREFIX_METRIC = "trend_metric."
PREFIX_SOURCE_ENABLED = "trend_source_enabled."


GROUP_SCORE = "score"
GROUP_SOURCE = "source"
GROUP_BUYER = "buyer"
GROUP_METRIC = "metric"
GROUP_SOURCE_ENABLED = "source_enabled"


def group_for_prefix(prefix: str) -> str:
    return {
        PREFIX_SCORE: GROUP_SCORE,
        PREFIX_SOURCE: GROUP_SOURCE,
        PREFIX_BUYER: GROUP_BUYER,
        PREFIX_METRIC: GROUP_METRIC,
        PREFIX_SOURCE_ENABLED: GROUP_SOURCE_ENABLED,
    }.get(prefix, "default")


async def _weights_from_table(
    session: AsyncSession,
    group: str,
    defaults: dict[str, float],
) -> dict[str, float]:
    stmt = select(TrendWeight).where(TrendWeight.group == group)
    rows = (await session.execute(stmt)).scalars().all()
    overrides = {row.key: row.value for row in rows}
    out = dict(defaults)
    out.update(overrides)
    return out


async def load_score_weights(session: AsyncSession) -> dict[str, float]:
    return await _weights_from_table(session, GROUP_SCORE, DEFAULT_SCORE_WEIGHTS)


async def load_source_weights(session: AsyncSession) -> dict[str, float]:
    return await _weights_from_table(session, GROUP_SOURCE, DEFAULT_SOURCE_WEIGHTS)


async def load_buyer_source_weights(session: AsyncSession) -> dict[str, float]:
    return await _weights_from_table(session, GROUP_BUYER, DEFAULT_BUYER_SOURCE_WEIGHTS)


async def load_metric_weights(session: AsyncSession) -> dict[str, float]:
    return await _weights_from_table(session, GROUP_METRIC, DEFAULT_METRIC_WEIGHTS)


async def load_all_weights(session: AsyncSession) -> dict[str, Any]:
    return {
        "score_weights": await load_score_weights(session),
        "source_weights": await load_source_weights(session),
        "buyer_source_weights": await load_buyer_source_weights(session),
        "metric_weights": await load_metric_weights(session),
    }


async def load_source_enabled_state(
    session: AsyncSession,
    source_keys: list[str] | tuple[str, ...] | set[str],
) -> dict[str, bool]:
    stmt = select(TrendWeight).where(TrendWeight.group == GROUP_SOURCE_ENABLED)
    rows = (await session.execute(stmt)).scalars().all()
    overrides = {row.key: bool(row.value) for row in rows}
    state = {key: DEFAULT_SOURCE_ENABLED.get(key, True) for key in source_keys}
    state.update({k: v for k, v in overrides.items() if k in state})
    return state


def scoring_version(weights: dict[str, Any]) -> str:
    raw = json.dumps(weights, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


async def save_weight(
    session: AsyncSession,
    group: str,
    key: str,
    value: float,
    description: str | None = None,
) -> None:
    stmt = select(TrendWeight).where(
        TrendWeight.group == group,
        TrendWeight.key == key,
    )
    existing = (await session.execute(stmt)).scalars().first()
    if existing:
        existing.value = float(value)
        if description is not None:
            existing.description = description
    else:
        session.add(
            TrendWeight(
                group=group,
                key=key,
                value=float(value),
                description=description,
            )
        )
    await session.flush()


async def save_weight_by_prefix(
    session: AsyncSession,
    prefix: str,
    key: str,
    value: float,
) -> None:
    await save_weight(
        session,
        group=group_for_prefix(prefix),
        key=key,
        value=value,
        description=f"Trend Scout {prefix.strip('.')} weight: {key}",
    )


def validate_score_weights(weights: dict[str, float]) -> list[str]:
    errors: list[str] = []
    required = set(DEFAULT_SCORE_WEIGHTS)
    provided = set(weights)
    missing = required - provided
    if missing:
        errors.append(f"Missing weights: {', '.join(sorted(missing))}")

    extra = provided - required
    if extra:
        errors.append(f"Unknown weights: {', '.join(sorted(extra))}")

    for key, val in weights.items():
        try:
            val = float(val)
        except TypeError, ValueError:
            errors.append(f"'{key}' is not a valid number")
            continue
        if val < -1.0 or val > 2.0:
            errors.append(f"'{key}' ({val}) is outside allowed range [-1.0, 2.0]")

    return errors


async def seed_default_weights(session: AsyncSession) -> list[str]:
    created: list[str] = []
    groups: list[tuple[str, dict[str, float]]] = [
        (GROUP_SCORE, DEFAULT_SCORE_WEIGHTS),
        (GROUP_SOURCE, DEFAULT_SOURCE_WEIGHTS),
        (GROUP_BUYER, DEFAULT_BUYER_SOURCE_WEIGHTS),
        (GROUP_METRIC, DEFAULT_METRIC_WEIGHTS),
    ]
    for group, defaults in groups:
        for key, default_val in defaults.items():
            stmt = select(TrendWeight).where(
                TrendWeight.group == group,
                TrendWeight.key == key,
            )
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                session.add(
                    TrendWeight(
                        group=group,
                        key=key,
                        value=float(default_val),
                        description=f"Trend Scout {group} weight default",
                    )
                )
                created.append(f"{group}:{key}")
    if created:
        await session.flush()
    return created
