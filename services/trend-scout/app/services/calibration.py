"""Calibration service for the Trend Scout microservice.

Runs the backtest, summarizes the results, and persists a calibration record.
A simple regression detector compares the latest two runs and surfaces
divergence.

Phase 3 stores calibration records in the trend_weights table under a special
group (``calibration_run:<timestamp>``) so the model footprint stays small
(we did not add a TrendCalibrationResult table in Phase 1).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TrendWeight
from app.services.backtest import (
    ActualSalesProvider,
    _generate_tuning_hints,
)
from app.services.backtest import (
    run_backtest as _run_backtest,
)

CALIBRATION_GROUP_PREFIX = "calibration_run:"


async def run_calibration(
    session: AsyncSession,
    trigger: str = "manual",
    lookback_reports: int = 12,
    sales_window_days: int = 60,
    actual_sales_provider: ActualSalesProvider | None = None,
) -> dict[str, Any]:
    """Run a backtest and persist the calibration record. Return the summary."""
    backtest = await _run_backtest(
        session,
        lookback_reports=lookback_reports,
        sales_window_days=sales_window_days,
        actual_sales_provider=actual_sales_provider,
    )
    summary = backtest.get("summary", {})
    record = {
        "trigger": trigger,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "report_count": backtest.get("report_count", 0),
        "summary": summary,
        "tuning_hints": _generate_tuning_hints(backtest),
        "status": backtest.get("status", "ok"),
    }
    if "error" in backtest:
        record["error"] = backtest["error"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    session.add(
        TrendWeight(
            group=f"{CALIBRATION_GROUP_PREFIX}{timestamp}",
            key="full",
            value=0.0,
            description=json.dumps(record, default=str),
        )
    )
    await session.commit()
    return record


async def get_calibration_history(session: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    stmt = (
        select(TrendWeight)
        .where(TrendWeight.group.like(f"{CALIBRATION_GROUP_PREFIX}%"))
        .order_by(TrendWeight.created_at.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    history: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.description or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload["_key"] = row.key
        payload["_group"] = row.group
        history.append(payload)
    return history


async def check_regression(
    session: AsyncSession,
    threshold_mae_delta: float = 0.5,
    threshold_precision_delta: float = 0.3,
) -> str | None:
    """Return a human-readable message if the latest run regressed, else None."""
    history = await get_calibration_history(session, limit=2)
    if len(history) < 2:
        return None
    prev, curr = history[1], history[0]
    prev_summary = prev.get("summary", {})
    curr_summary = curr.get("summary", {})
    messages: list[str] = []
    if (
        curr_summary.get("mae") is not None
        and prev_summary.get("mae") is not None
        and curr_summary["mae"] > prev_summary["mae"] + threshold_mae_delta
    ):
        messages.append(f"MAE increased from {prev_summary['mae']:.3f} to {curr_summary['mae']:.3f}")
    if (
        curr_summary.get("top_hit_rate") is not None
        and prev_summary.get("top_hit_rate") is not None
        and curr_summary["top_hit_rate"] < prev_summary["top_hit_rate"] - threshold_precision_delta
    ):
        messages.append(
            f"Top-5 hit rate dropped from {prev_summary['top_hit_rate']:.1%} to {curr_summary['top_hit_rate']:.1%}"
        )
    return "; ".join(messages) if messages else None
