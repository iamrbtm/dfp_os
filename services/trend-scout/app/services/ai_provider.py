"""AI provider abstraction for the Trend Scout microservice.

Wraps the OpenAI client (and future providers) to produce a deterministic
synthesis of opportunity scores when AI is disabled. The synthesis is a
simple deterministic copy of the input data; it never invents metrics.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _deterministic_summary(
    top_opportunities: list[dict[str, Any]],
    growing: list[dict[str, Any]],
    declining: list[dict[str, Any]],
) -> str:
    lines = ["# Trend Scout Weekly Summary (deterministic — AI synthesis disabled)"]
    lines.append("")
    lines.append(f"Top opportunities: {len(top_opportunities)}")
    for opp in top_opportunities[:5]:
        title = opp.get("title") or opp.get("keyword") or "unknown"
        score = opp.get("score", 0.0)
        action = opp.get("recommended_action", "watch")
        lines.append(f"- {title} (score={score:.2f}, action={action})")
    lines.append("")
    lines.append(f"Growing categories: {len(growing)}")
    for cat in growing[:5]:
        lines.append(f"- {cat.get('name', cat.get('keyword', 'unknown'))}")
    lines.append("")
    lines.append(f"Declining categories: {len(declining)}")
    for cat in declining[:5]:
        lines.append(f"- {cat.get('name', cat.get('keyword', 'unknown'))}")
    return "\n".join(lines)


async def synthesize_report(
    top_opportunities: list[dict[str, Any]],
    growing: list[dict[str, Any]],
    declining: list[dict[str, Any]],
) -> str:
    """Produce a human-readable report summary.

    If an OpenAI API key is configured and ``ai_provider == 'openai'``, the
    LLM produces the summary. Otherwise the deterministic fallback runs.
    Failures fall back to the deterministic path so the pipeline never
    breaks because of an AI outage.
    """
    if settings.ai_provider == "openai" and settings.openai_api_key:
        try:
            return await _openai_summarize(
                top_opportunities=top_opportunities,
                growing=growing,
                declining=declining,
            )
        except Exception as exc:
            logger.warning("OpenAI summarize failed (%s), falling back to deterministic", exc)

    return _deterministic_summary(
        top_opportunities=top_opportunities,
        growing=growing,
        declining=declining,
    )


async def _openai_summarize(
    top_opportunities: list[dict[str, Any]],
    growing: list[dict[str, Any]],
    declining: list[dict[str, Any]],
) -> str:
    """Call the configured model and return its summary text."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    payload = {
        "top_opportunities": top_opportunities[:25],
        "growing_categories": growing[:10],
        "declining_categories": declining[:10],
    }
    prompt = (
        "You are summarizing a weekly Trend Scout report for a 3D printing small "
        "business. Be concise, factual, and only reference the data in the payload. "
        "Do not invent metrics, sources, or numbers. Output is markdown.\n\n"
        f"DATA:\n```json\n{json.dumps(payload, indent=2, default=str)}\n```"
    )
    response = await client.chat.completions.create(
        model=settings.openai_model_trend_scout,
        messages=[
            {"role": "system", "content": "You produce concise markdown summaries."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    content = response.choices[0].message.content or ""
    return content.strip() or _deterministic_summary(
        top_opportunities,
        growing,
        declining,
    )
