from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.models.trend import TrendCalibrationResult


def run_and_store_calibration(
    trigger: str = "manual",
    lookback_reports: int = 12,
    sales_window_days: int = 60,
) -> TrendCalibrationResult:
    from app.services.trend_scout_backtest import run_backtest

    result = TrendCalibrationResult(
        run_date=datetime.now(timezone.utc),
        trigger=trigger,
    )

    try:
        backtest = run_backtest(db.session, lookback_reports=lookback_reports, sales_window_days=sales_window_days)

        result.report_count = backtest.get("report_count", 0)
        result.score_count = backtest.get("score_count", 0)
        stats = backtest.get("stats", {})
        result.mae = stats.get("mae")
        result.rmse = stats.get("rmse")
        result.precision_at_high_score = stats.get("precision_at_high_score")
        result.recall_of_sellers = stats.get("recall_of_sellers")
        result.f1_score = stats.get("f1")
        result.zero_seller_rate = stats.get("zero_seller_rate")
        result.avg_predicted_score = stats.get("avg_predicted_score")
        result.total_units_sold = stats.get("total_units_sold", 0)
        result.component_analysis = backtest.get("component_analysis")
        result.top_k_analysis = backtest.get("top_k_analysis")
        result.action_analysis = backtest.get("action_analysis")
        result.tuning_hints = backtest.get("tuning_hints")
        result.current_weights = backtest.get("current_weights")
        result.predictions_sample = backtest.get("predictions", [])[:100]
    except Exception as exc:
        result.error_message = str(exc)

    db.session.add(result)
    db.session.commit()
    return result


def get_calibration_history(limit: int = 20) -> list[TrendCalibrationResult]:
    return (
        db.session.query(TrendCalibrationResult)
        .order_by(TrendCalibrationResult.run_date.desc())
        .limit(limit)
        .all()
    )


def check_regression(
    threshold_mae: float = 0.5,
    threshold_precision: float = 0.3,
) -> str | None:
    records = (
        db.session.query(TrendCalibrationResult)
        .order_by(TrendCalibrationResult.run_date.desc())
        .limit(2)
        .all()
    )
    if len(records) < 2:
        return None
    prev, curr = records[1], records[0]
    if curr.mae is None or prev.mae is None:
        return None
    messages = []
    if curr.mae > prev.mae + threshold_mae:
        messages.append(f"MAE increased from {prev.mae:.3f} to {curr.mae:.3f}")
    if curr.precision_at_high_score is not None and prev.precision_at_high_score is not None:
        if curr.precision_at_high_score < prev.precision_at_high_score - threshold_precision:
            messages.append(
                f"Precision@High dropped from {prev.precision_at_high_score:.1%} to {curr.precision_at_high_score:.1%}"
            )
    return "; ".join(messages) if messages else None
