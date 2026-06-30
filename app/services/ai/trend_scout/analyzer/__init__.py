from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.trend import TrendReport

from .new_category_discovery import discover_new_categories
from .trend_detector import (
    compute_top_opportunities,
    compute_velocity_and_momentum,
)

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = (
    "You are a trend analyst for a 3D printing business. "
    "Given the following trend data, velocity analysis, emerging category clusters, "
    "and top opportunities with buyer-intent decision-matrix scores, write a concise weekly report summary. "
    "Focus on:\n"
    "- What products/categories are rising in demand\n"
    "- What is declining\n"
    "- New or unexpected category clusters detected\n"
    "- Actionable recommendations for what to print, stock, or prepare\n\n"
    "Be specific, practical, and ground claims in the data.\n\n"
    "Trend Data:\n{data}"
)


def run_analysis(
    db_session: Session,
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> TrendReport | None:
    velocity_data = compute_velocity_and_momentum(db_session)
    opportunities = compute_top_opportunities(db_session)
    clusters = discover_new_categories(db_session, api_key=openai_api_key)

    synthesis_data = {
        "velocity": velocity_data.get("velocity", {}),
        "momentum": velocity_data.get("momentum", {}),
        "cross_source": velocity_data.get("cross_source", {}),
        "top_opportunities": opportunities,
        "emerging_clusters": clusters.get("clusters", []),
    }

    summary = _synthesize_report(synthesis_data, openai_api_key, openai_model)
    used_ai_synthesis = bool(summary)

    if not summary:
        summary = _deterministic_summary(synthesis_data, clusters)

    declining = sorted(
        {
            kw
            for source_mom in velocity_data.get("momentum", {}).values()
            for kw, info in source_mom.items()
            if info.get("direction") == "down"
        }
    )[:20]

    report = TrendReport(
        report_date=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        summary=summary,
        top_opportunities=opportunities,
        growing_categories=[c["top_phrases"] for c in clusters.get("clusters", [])],
        declining_trends=declining,
        pipeline_meta={
            "velocity_metadata": velocity_data.get("metadata", {}),
            "clusters_found": clusters.get("total_clusters_found", 0),
            "titles_analyzed": clusters.get("total_titles_analyzed", 0),
            "cluster_notes": clusters.get("notes"),
            "analysis_mode": "ai_synthesis" if used_ai_synthesis else "deterministic",
            "opportunity_scoring": {
                "version": "buyer_intent_matrix_v1",
                "formula": (
                    "purchase_intent + trend_velocity + price_resilience + "
                    "low_saturation + local_fit + production_fit - license_risk"
                ),
                "includes_current_products": True,
            },
        },
    )
    db_session.add(report)
    db_session.commit()
    logger.info("TrendReport #%d saved", report.id)
    return report


def _synthesize_report(
    data: dict[str, Any],
    api_key: str,
    model: str,
) -> str:
    if not api_key:
        logger.warning("No OpenAI API key; skipping AI synthesis")
        return ""

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": SYNTHESIS_PROMPT.format(data=json.dumps(data, indent=2)),
                }
            ],
            timeout=60,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as exc:
        logger.warning("AI report synthesis failed: %s", exc)
        return ""


def _deterministic_summary(data: dict[str, Any], clusters: dict[str, Any]) -> str:
    opportunities = data.get("top_opportunities", [])[:5]
    cross_source = data.get("cross_source", {}).get("appearing_across_multiple_sources", {})
    cluster_list = clusters.get("clusters", [])[:5]

    lines = [
        "Trend Scout completed using deterministic scoring because AI synthesis is unavailable.",
    ]
    if opportunities:
        formatted = ", ".join(f"{item['keyword']} ({item['score']})" for item in opportunities)
        lines.append(f"Top scored opportunities: {formatted}.")
    else:
        lines.append("No actionable opportunities were found in snapshots with real item data.")

    if cross_source:
        confirmed = ", ".join(list(cross_source.keys())[:5])
        lines.append(f"Cross-source confirmation appeared for: {confirmed}.")

    if cluster_list:
        phrases = ", ".join(
            ", ".join(cluster.get("top_phrases", [])[:3])
            for cluster in cluster_list
            if cluster.get("top_phrases")
        )
        if phrases:
            lines.append(f"Emerging title patterns: {phrases}.")

    notes = clusters.get("notes")
    if notes:
        lines.append(f"Analysis note: {notes}.")

    return "\n\n".join(lines)
