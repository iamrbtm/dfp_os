from __future__ import annotations

from flask import jsonify, render_template, session

from app.blueprints.trend_scout import bp
from app.celery_app import celery
from app.extensions import db
from app.models import TrendReport, UserRole
from app.utils.auth import roles_required


@bp.get("/")
@roles_required(UserRole.ADMIN)
def index():
    latest = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).first()
    all_reports = (
        db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).limit(20).all()
    )
    return render_template(
        "trend_scout/index.html",
        latest=latest,
        all_reports=all_reports,
    )


@bp.get("/api/latest")
@roles_required(UserRole.ADMIN)
def latest_report():
    report = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).first()
    if not report:
        return jsonify({"found": False})
    return jsonify(
        {
            "found": True,
            "id": report.id,
            "report_date": report.report_date.isoformat(),
            "summary": report.summary,
            "top_opportunities": report.top_opportunities,
            "growing_categories": report.growing_categories,
            "declining_trends": report.declining_trends,
            "pipeline_meta": report.pipeline_meta,
            "created_at": report.created_at.isoformat(),
        }
    )


@bp.post("/run")
@roles_required(UserRole.ADMIN)
def run_pipeline():
    from app.tasks.trend_scout import trend_scout_pipeline

    task = trend_scout_pipeline.delay()
    session["trend_scout_task_id"] = task.id
    return jsonify({"task_id": task.id, "status": "dispatched"})


@bp.get("/run/status/<task_id>")
@roles_required(UserRole.ADMIN)
def run_status(task_id: str):
    result = celery.AsyncResult(task_id)
    meta = result.info if hasattr(result, "info") and result.info else {}
    return jsonify(
        {
            "task_id": task_id,
            "state": result.state,
            "meta": meta,
            "result": result.result if result.ready() else None,
        }
    )


@bp.get("/pipeline/progress")
@roles_required(UserRole.ADMIN)
def pipeline_progress():
    task_id = session.get("trend_scout_task_id")
    if not task_id:
        return '<div id="pipeline-progress" class="hidden"></div>'

    result = celery.AsyncResult(task_id)
    meta = result.info if hasattr(result, "info") and result.info else {}

    if result.state in ("SUCCESS", "FAILURE"):
        session.pop("trend_scout_task_id", None)
        return '<div id="pipeline-progress" class="hidden"></div>'

    current = meta.get("current", 0)
    total = meta.get("total", 1)
    step = meta.get("step", "")
    status = meta.get("status", "running")
    percent = int((current / total) * 100) if total > 0 else 0

    return render_template(
        "trend_scout/_pipeline_progress.html",
        current=current,
        total=total,
        percent=percent,
        step=step,
        status=status,
        task_running=True,
    )


@bp.get("/api/reports")
@roles_required(UserRole.ADMIN)
def report_list():
    reports = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).limit(50).all()
    return jsonify(
        [
            {
                "id": r.id,
                "report_date": r.report_date.isoformat(),
                "summary": (r.summary or "")[:200],
                "opportunity_count": len(r.top_opportunities) if r.top_opportunities else 0,
                "growing_count": len(r.growing_categories) if r.growing_categories else 0,
            }
            for r in reports
        ]
    )
