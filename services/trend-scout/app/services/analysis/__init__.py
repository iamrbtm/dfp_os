"""Analyzer package for the Trend Scout microservice.

Exposes:
- run_analysis(session, business_id, source_health) -> TrendReport | None
- compute_velocity_and_momentum(session) -> dict
- compute_top_opportunities(session, ...) -> list[dict]
- discover_new_categories(session, ...) -> dict

The Phase 3 implementation is intentionally simplified compared to the
1,131-line monolith version: velocity is recomputed from recent snapshots,
opportunity scores use a per-keyword aggregate, and category discovery is
delegated to a future DBSCAN/embedding step. Behavior parity is preserved at
the data-model level (TrendReport / TrendOpportunityScore / SourceHealthRecord
rows look the same); the algorithmic depth lives in the heavier trend_detector
which lands fully in Phase 10.
"""

from __future__ import annotations

from app.services.analysis.new_category_discovery import discover_new_categories
from app.services.analysis.opportunity_scoring import compute_opportunity_score
from app.services.analysis.trend_detector import (
    compute_growing_and_declining,
    compute_top_opportunities,
    compute_velocity_and_momentum,
    recommended_action_for_score,
    score_breakdown_for_opportunity,
)

__all__ = [
    "compute_top_opportunities",
    "compute_velocity_and_momentum",
    "compute_growing_and_declining",
    "score_breakdown_for_opportunity",
    "recommended_action_for_score",
    "compute_opportunity_score",
    "discover_new_categories",
]
