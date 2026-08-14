"""Backtest service for the Trend Scout microservice.

Compares past TrendOpportunityScore rows against actual sales to measure how
well the scoring math predicts outcomes. In Phase 3 the actual sales come
from a caller-supplied provider so the microservice can run backtests without
in-process access to the main app's Order/PosSale tables. The Flask app will
expose a ``/api/internal/orders-since`` endpoint in Phase 6 that the worker
plugs into ``actual_sales_provider``.

Backtest output shape:

    {
      "status": "ok" | "no_data",
      "report_count": int,
      "sales_window_days": int,
      "predictions": [...],
      "summary": {
        "rmse": float, "mae": float, "r2": float,
        "top_hit_rate": float, "precision_at_5": float,
      },
      "tuning_hints": [...]  # optional
    }
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TrendOpportunityScore, TrendReport

ActualSalesProvider = Callable[[int, datetime, int], Awaitable[dict[str, Any]]]


async def _default_actual_sales_provider(product_id: int, after: datetime, days: int) -> dict[str, Any]:
    """Fallback when no provider is supplied. Returns zero sales."""
    return {"quantity": 0, "revenue": 0.0, "order_count": 0}


def _rmse(predictions: list[float], actuals: list[float]) -> float:
    if not predictions:
        return 0.0
    total = sum((p - a) ** 2 for p, a in zip(predictions, actuals, strict=False))
    return round(math.sqrt(total / len(predictions)), 4)


def _mae(predictions: list[float], actuals: list[float]) -> float:
    if not predictions:
        return 0.0
    total = sum(abs(p - a) for p, a in zip(predictions, actuals, strict=False))
    return round(total / len(predictions), 4)


def _r2(predictions: list[float], actuals: list[float]) -> float:
    if len(actuals) < 2:
        return 0.0
    mean_actual = sum(actuals) / len(actuals)
    ss_res = sum((a - p) ** 2 for a, p in zip(actuals, predictions, strict=False))
    ss_tot = sum((a - mean_actual) ** 2 for a in actuals)
    if ss_tot == 0:
        return 0.0
    return round(1.0 - ss_res / ss_tot, 4)


def _precision_at_k(predictions: list[dict[str, Any]], k: int = 5) -> float:
    if not predictions:
        return 0.0
    top_k = predictions[:k]
    hits = sum(1 for p in top_k if p["actual_quantity_sold"] > 0)
    return round(hits / max(1, len(top_k)), 4)


async def run_backtest(
    session: AsyncSession,
    lookback_reports: int = 12,
    sales_window_days: int = 60,
    actual_sales_provider: ActualSalesProvider | None = None,
) -> dict[str, Any]:
    """Re-score past opportunities against their actual sales performance."""
    provider = actual_sales_provider or _default_actual_sales_provider

    stmt = select(TrendReport).order_by(TrendReport.report_date.desc()).limit(lookback_reports)
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()

    if not rows:
        return {
            "status": "no_data",
            "message": "No TrendReport records found. Run a pipeline first.",
            "report_count": 0,
            "sales_window_days": sales_window_days,
        }

    predictions: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for report in rows:
        score_stmt = select(TrendOpportunityScore).where(TrendOpportunityScore.report_id == report.id)
        opportunities = list((await session.execute(score_stmt)).scalars().all())
        for opportunity in opportunities:
            entries: list[dict[str, Any]] = []
            product_id = int(getattr(opportunity, "product_id", 0) or 0)
            actual = await provider(product_id, report.report_date, sales_window_days)
            entries.append(
                {
                    "report_id": report.id,
                    "report_date": report.report_date.isoformat(),
                    "keyword": opportunity.keyword,
                    "source": opportunity.source,
                    "predicted_score": float(opportunity.score),
                    "actual_quantity_sold": int(actual.get("quantity", 0)),
                    "actual_revenue": float(actual.get("revenue", 0.0)),
                    "actual_order_count": int(actual.get("order_count", 0)),
                    "purchase_intent": float(opportunity.purchase_intent),
                    "velocity": float(opportunity.velocity),
                    "license_risk": opportunity.license_risk,
                    "local_relevance": float(opportunity.local_relevance),
                    "scoring_version": report.scoring_version,
                    "evaluated_at": now.isoformat(),
                }
            )
            predictions.extend(entries)

    predictions.sort(key=lambda p: -p["predicted_score"])

    pred_scores = [p["predicted_score"] for p in predictions]
    actual_sales = [p["actual_quantity_sold"] for p in predictions]
    summary = {
        "rmse": _rmse(pred_scores, actual_sales),
        "mae": _mae(pred_scores, actual_sales),
        "r2": _r2(pred_scores, actual_sales),
        "top_hit_rate": _precision_at_k(predictions, k=5),
        "precision_at_5": _precision_at_k(predictions, k=5),
        "total_predictions": len(predictions),
    }

    return {
        "status": "ok",
        "report_count": len(rows),
        "sales_window_days": sales_window_days,
        "lookback_reports": lookback_reports,
        "summary": summary,
        "predictions": predictions[:100],
    }


def _generate_tuning_hints(backtest_result: dict[str, Any]) -> list[str]:
    """Suggest weight adjustments when the backtest reveals weaknesses."""
    hints: list[str] = []
    summary = backtest_result.get("summary", {})
    if summary.get("top_hit_rate", 1.0) < 0.4:
        hints.append(
            "top-5 hit rate is low; consider increasing purchase_intent weight or tightening the rank-order cutoff."
        )
    if summary.get("rmse", 0.0) > 30.0:
        hints.append(
            "high RMSE: opportunity scores are noisy; consider lowering trend_velocity or increasing price_resilience."
        )
    if summary.get("r2", 1.0) < 0.0:
        hints.append(
            "R^2 is negative: scoring is worse than baseline mean; consider a full "
            "weight re-calibration via the calibration service."
        )
    return hints
