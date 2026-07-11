from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any


from app.extensions import db
from app.models.trend import SourceHealthRecord, TrendOpportunityScore, TrendReport, TrendSnapshot

logger = logging.getLogger(__name__)

DEFAULT_KEEP_REPORTS = 52
DEFAULT_KEEP_DAYS = 365


def prune_old_data(
    keep_reports: int = DEFAULT_KEEP_REPORTS,
    keep_days: int = DEFAULT_KEEP_DAYS,
    dry_run: bool = False,
) -> dict[str, Any]:
    oldest_allowed = datetime.now(timezone.utc) - timedelta(days=keep_days)

    cutoff_report = (
        db.session.query(TrendReport)
        .order_by(TrendReport.report_date.desc())
        .offset(keep_reports)
        .first()
    )

    conditions = []
    if cutoff_report:
        conditions.append(TrendReport.report_date < cutoff_report.report_date)
    conditions.append(TrendReport.report_date < oldest_allowed)
    prune_before = min(
        cutoff_report.report_date if cutoff_report else oldest_allowed,
        oldest_allowed,
    )

    report_ids_to_prune = [
        r.id for r in db.session.query(TrendReport.id)
        .filter(TrendReport.report_date < prune_before)
        .all()
    ]

    if not report_ids_to_prune:
        return {"status": "none", "message": "No data to prune.", "pruned_reports": 0, "pruned_snapshots": 0}

    snapshot_count = db.session.query(TrendSnapshot).count()
    old_snapshots = (
        db.session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at < oldest_allowed)
        .all()
    )

    counts = {
        "pruned_reports": len(report_ids_to_prune),
        "pruned_snapshots": len(old_snapshots),
        "pruned_scores": db.session.query(TrendOpportunityScore)
            .filter(TrendOpportunityScore.report_id.in_(report_ids_to_prune))
            .count(),
        "pruned_health_records": db.session.query(SourceHealthRecord)
            .filter(SourceHealthRecord.report_id.in_(report_ids_to_prune))
            .count(),
        "snapshot_count_before": snapshot_count,
    }

    if dry_run:
        return {"status": "dry_run", **counts}

    db.session.query(SourceHealthRecord).filter(
        SourceHealthRecord.report_id.in_(report_ids_to_prune)
    ).delete(synchronize_session=False)

    db.session.query(TrendOpportunityScore).filter(
        TrendOpportunityScore.report_id.in_(report_ids_to_prune)
    ).delete(synchronize_session=False)

    db.session.query(TrendReport).filter(
        TrendReport.id.in_(report_ids_to_prune)
    ).delete(synchronize_session=False)

    for snap in old_snapshots:
        db.session.delete(snap)

    db.session.commit()

    counts["snapshot_count_after"] = db.session.query(TrendSnapshot).count()
    counts["report_count_after"] = db.session.query(TrendReport).count()
    counts["status"] = "pruned"

    logger.info(
        "Pruned %d reports, %d scores, %d health records, %d snapshots",
        counts["pruned_reports"],
        counts["pruned_scores"],
        counts["pruned_health_records"],
        counts["pruned_snapshots"],
    )

    return counts
