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
    "and top opportunities, write a concise weekly report summary. "
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
    clusters = discover_new_categories(
        db_session, api_key=openai_api_key
    )

    synthesis_data = {
        "velocity": velocity_data.get("velocity", {}),
        "momentum": velocity_data.get("momentum", {}),
        "cross_source": velocity_data.get("cross_source", {}),
        "top_opportunities": opportunities,
        "emerging_clusters": clusters.get("clusters", []),
    }

    summary = _synthesize_report(synthesis_data, openai_api_key, openai_model)

    if not summary:
        summary = (
            "Analysis complete but AI synthesis was unavailable "
            "(no API key or API error). Review the numeric trend data manually."
        )

    report = TrendReport(
        report_date=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        summary=summary,
        top_opportunities=opportunities,
        growing_categories=[
            c["top_phrases"]
            for c in clusters.get("clusters", [])
        ],
        declining_trends=[
            kw
            for source_mom in velocity_data.get("momentum", {}).values()
            for kw, info in source_mom.items()
            if info.get("direction") == "down"
        ],
        pipeline_meta={
            "velocity_metadata": velocity_data.get("metadata", {}),
            "clusters_found": clusters.get("total_clusters_found", 0),
            "titles_analyzed": clusters.get("total_titles_analyzed", 0),
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
                    "content": SYNTHESIS_PROMPT.format(
                        data=json.dumps(data, indent=2)
                    ),
                }
            ],
            timeout=60,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as exc:
        logger.warning("AI report synthesis failed: %s", exc)
        return ""
