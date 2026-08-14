"""Opportunity scoring helpers for the Trend Scout microservice.

Phase 3 integrates the scoring math into ``trend_detector.py``. This module
exists as a separate surface for callers that want to re-score a single
opportunity without re-running the full pipeline (Phase 5 API endpoints,
Phase 6 Flask proxy).
"""

from __future__ import annotations

from typing import Any

from app.services.weights import DEFAULT_SCORE_WEIGHTS


def compute_opportunity_score(
    opportunity: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> float:
    """Apply the 7-dimension scoring formula and return a 0..100 score.

    The math is the same as ``trend_detector`` so callers can re-rank
    opportunities consistently.
    """
    weight_map = weights or DEFAULT_SCORE_WEIGHTS
    score_weights = weights if isinstance(weights, dict) and weights else DEFAULT_SCORE_WEIGHTS
    score_weights = score_weights if any(score_weights.values()) else DEFAULT_SCORE_WEIGHTS

    weighted_total = sum(
        opportunity.get(key, 0.0) * float(weight_map.get(key, 1.0))
        for key in (
            "purchase_intent",
            "velocity",
            "price_resilience",
            "low_saturation",
            "local_relevance",
            "production_fit",
            "license_risk",
        )
    )
    license_risk = float(opportunity.get("license_risk", 0.0))
    score_0_100 = max(0.0, min(100.0, 50.0 + weighted_total * 50.0 - license_risk * 25.0))
    return round(score_0_100, 2)
