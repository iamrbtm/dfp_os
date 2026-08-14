"""High-level analyzer orchestration for the Trend Scout microservice.

Composes:
1. compute_velocity_and_momentum  -> cross-source trend signals
2. compute_top_opportunities     -> ranked opportunity list
3. discover_new_categories       -> NLP/embedding clusters
4. synthesize_report             -> AI summary (or deterministic fallback)
5. Persist TrendReport + TrendOpportunityScore + SourceHealthRecord rows.

This is the microservice equivalent of the monolith's
``app.services.ai.trend_scout.analyzer.run_analysis`` with async DB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SourceHealthRecord, TrendOpportunityScore, TrendReport
from app.services.ai_provider import synthesize_report
from app.services.analysis.new_category_discovery import discover_new_categories
from app.services.analysis.trend_detector import (
    compute_growing_and_declining,
    compute_top_opportunities,
    compute_velocity_and_momentum,
)
from app.services.weights import load_all_weights, scoring_version

logger = logging.getLogger(__name__)


async def _persist_opportunity_scores(
    session: AsyncSession,
    report: TrendReport,
    opportunities: list[dict[str, Any]],
) -> int:
    rows: list[TrendOpportunityScore] = []
    for opp in opportunities:
        rows.append(
            TrendOpportunityScore(
                report_id=report.id,
                keyword=opp.get("keyword", ""),
                source=opp.get("source", ""),
                score=float(opp.get("score", 0.0)),
                score_breakdown=opp.get("score_breakdown", {}),
                recommended_action=opp.get("recommended_action", "watch"),
                velocity=float(opp.get("velocity", 0.0)),
                momentum=float(opp.get("momentum", 0.0)),
                purchase_intent=float(opp.get("purchase_intent", 0.0)),
                license_risk=str(opp.get("license_risk", "unknown")),
                local_relevance=float(opp.get("local_relevance", 0.0)),
                dismissed=False,
            )
        )
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def _persist_source_health(
    session: AsyncSession,
    report: TrendReport,
    source_health: list[dict[str, Any]] | None,
) -> int:
    if not source_health:
        return 0
    rows: list[SourceHealthRecord] = []
    for sh in source_health:
        rows.append(
            SourceHealthRecord(
                report_id=report.id,
                source=sh.get("source", "unknown"),
                status=sh.get("status", "success"),
                keyword=sh.get("keyword"),
                item_count=sh.get("item_count", 0),
                error_message=sh.get("error_message"),
                throttled=False,
                throttle_reason=None,
                scraped_at=sh.get("scraped_at") or datetime.now(timezone.utc),
                metadata_json=sh.get("metadata") or {},
            )
        )
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def run_analysis(
    session: AsyncSession,
    business_id: int | None = None,
    source_health: list[dict[str, Any]] | None = None,
) -> TrendReport | None:
    """Run the full analyzer pipeline and persist the resulting report.

    Returns the TrendReport row on success, None if no opportunities existed.
    """
    weights = await load_all_weights(session)
    version = scoring_version(weights)

    velocity = await compute_velocity_and_momentum(session)
    opportunities = await compute_top_opportunities(
        session,
        weights=weights,
        business_id=business_id,
    )
    clusters = await discover_new_categories(session)
    growing, declining = compute_growing_and_declining(velocity, clusters)

    summary = await synthesize_report(
        top_opportunities=opportunities[:25],
        growing=[{"name": g} for g in growing],
        declining=[{"name": d} for d in declining],
    )

    report = TrendReport(
        report_date=datetime.now(timezone.utc),
        summary=summary,
        top_opportunities=opportunities,
        growing_categories=[{"name": g} for g in growing],
        declining_categories=[{"name": d} for d in declining],
        scoring_version=version,
        business_id=business_id,
        pipeline_metadata={
            "scoring_weights_version": version,
            "clusters_found": clusters.get("total_clusters_found", 0),
            "titles_analyzed": clusters.get("total_titles_analyzed", 0),
            "cluster_notes": clusters.get("notes"),
            "velocity_metadata": velocity.get("metadata", {}),
        },
    )
    session.add(report)
    await session.flush()

    score_count = await _persist_opportunity_scores(session, report, opportunities)
    health_count = await _persist_source_health(session, report, source_health)

    await session.commit()
    logger.info(
        "TrendReport #%d persisted: %d opportunity scores, %d source health rows",
        report.id,
        score_count,
        health_count,
    )
    return report
