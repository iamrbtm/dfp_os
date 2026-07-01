from __future__ import annotations

from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.celery_app import celery
from app.extensions import db
from app.services.audit import record_audit_event
from app.services.notification import create_notification
from app.services.trend_scout_calibration import check_regression, run_and_store_calibration

logger = get_task_logger(__name__)


@celery.task(
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=660,
)
def calibrate_trend_scout(self) -> dict:
    logger.info("Starting scheduled trend scout calibration")
    try:
        result = run_and_store_calibration(
            trigger="scheduled",
            lookback_reports=12,
            sales_window_days=60,
        )
        logger.info(
            "Calibration complete: id=%d mae=%s precision=%s",
            result.id,
            result.mae,
            result.precision_at_high_score,
        )

        record_audit_event(
            action="trend_scout.calibration.completed",
            entity_type="trend_calibration_result",
            entity_id=str(result.id),
            metadata={
                "trigger": "scheduled",
                "report_count": result.report_count,
                "mae": result.mae,
                "precision": result.precision_at_high_score,
                "f1": result.f1_score,
            },
            source_module=__name__,
        )

        regression_msg = check_regression()
        if regression_msg:
            logger.warning("Calibration regression detected: %s", regression_msg)
            create_notification(
                notification_type="trend_scout_calibration_regression",
                title="Trend Scout calibration regression",
                message=regression_msg,
                link="/admin/trend-scout/calibration",
            )
            record_audit_event(
                action="trend_scout.calibration.regression",
                entity_type="trend_calibration_result",
                entity_id=str(result.id),
                metadata={"regression": regression_msg},
                source_module=__name__,
            )

        return {
            "success": True,
            "calibration_id": result.id,
            "mae": result.mae,
            "regression": regression_msg,
        }
    except Exception as exc:
        logger.exception("Calibration failed")
        record_audit_event(
            action="trend_scout.calibration.failed",
            entity_type="system",
            entity_id="calibration",
            metadata={"error": str(exc), "trigger": "scheduled"},
            source_module=__name__,
        )
        raise self.retry(exc=exc)
