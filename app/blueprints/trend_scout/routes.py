from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from app.blueprints.trend_scout import bp
from app.celery_app import celery
from app.extensions import db
from app.models import (
    PrintJob,
    PrintJobStatus,
    Product,
    SourceHealthRecord,
    TrendOpportunityScore,
    TrendReport,
    UserRole,
)
from app.services.audit import record_audit_event
from app.utils.auth import roles_required

_PROVIDER_CONFIG_CHECKS: dict[str, list[tuple[str, str]]] = {
    "etsy": [("ETSY_API_KEY", "API key")],
    "google_trends": [("SERPAPI_API_KEY", "SerpAPI key")],
    "tiktok": [("TIKTOK_RESEARCH_ACCESS_TOKEN", "Research API token")],
    "pinterest": [("PINTEREST_API_KEY", "API key")],
    "makerworld": [],
    "printables": [],
    "myminifactory": [],
    "reddit": [],
    "bgg": [],
    "internal_demand": [],
}


def _provider_setup_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for source, checks in _PROVIDER_CONFIG_CHECKS.items():
        if not checks:
            status[source] = {"configured": True, "needs_env": [], "missing_env": []}
        else:
            missing = [label for env_name, label in checks if not os.getenv(env_name)]
            status[source] = {
                "configured": len(missing) == 0,
                "needs_env": [env_name for env_name, _ in checks],
                "missing_env": missing,
            }
    return status


def _freshness_label(scraped_at: datetime | None) -> str:
    if not scraped_at:
        return "never"
    delta = datetime.now(timezone.utc) - scraped_at
    if delta.days > 0:
        return f"{delta.days}d ago"
    if delta.seconds >= 3600:
        return f"{delta.seconds // 3600}h ago"
    return f"{max(1, delta.seconds // 60)}m ago"


def _freshness_score(scraped_at: datetime | None) -> int:
    if not scraped_at:
        return 0
    delta = datetime.now(timezone.utc) - scraped_at
    if delta.days == 0:
        return 100
    if delta.days <= 1:
        return 80
    if delta.days <= 3:
        return 60
    if delta.days <= 7:
        return 40
    return 20


@bp.get("/")
@roles_required(UserRole.ADMIN)
def index():
    latest = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).first()
    all_reports = (
        db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).limit(20).all()
    )
    source_health = []
    if latest:
        source_health = (
            db.session.query(SourceHealthRecord)
            .filter(SourceHealthRecord.report_id == latest.id)
            .order_by(SourceHealthRecord.source)
            .all()
        )
    provider_setup = _provider_setup_status()
    return render_template(
        "trend_scout/index.html",
        latest=latest,
        all_reports=all_reports,
        source_health=source_health,
        provider_setup=provider_setup,
        freshness_label=_freshness_label,
        freshness_score=_freshness_score,
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
    from app.services.ai.trend_scout import FETCHERS as _TS_FETCHERS
    from app.tasks.trend_scout import trend_scout_pipeline
    from app.services.trend_scout_task_monitor import create_task_run

    task = trend_scout_pipeline.delay()
    session["trend_scout_task_id"] = task.id

    try:
        create_task_run(
            task_id=f"manual-{task.id}",
            trigger="manual",
            total_steps=len(_TS_FETCHERS) + 1,
            celery_task_id=task.id,
        )
    except Exception:
        pass

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


@bp.get("/api/persisted-scores")
@roles_required(UserRole.ADMIN)
def persisted_scores():
    report = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).first()
    if not report:
        return jsonify({"found": False, "scores": []})

    scores = (
        db.session.query(TrendOpportunityScore)
        .filter(TrendOpportunityScore.report_id == report.id)
        .order_by(TrendOpportunityScore.rank.asc().nulls_last(), TrendOpportunityScore.opportunity_score.desc())
        .all()
    )

    return jsonify({
        "found": True,
        "report_id": report.id,
        "report_date": report.report_date.isoformat(),
        "scores": [
            {
                "id": s.id,
                "keyword": s.keyword,
                "title": s.title or s.keyword,
                "candidate_type": s.candidate_type,
                "product_id": s.product_id,
                "opportunity_score": s.opportunity_score,
                "purchase_intent": s.purchase_intent,
                "trend_velocity": s.trend_velocity,
                "price_resilience": s.price_resilience,
                "low_saturation": s.low_saturation,
                "local_fit": s.local_fit,
                "production_fit": s.production_fit,
                "license_risk": s.license_risk,
                "action": s.action,
                "inventory_available": s.inventory_available,
                "base_price": str(s.base_price),
                "license_status": s.license_status,
                "rank": s.rank,
                "sources": s.sources,
                "score_breakdown": s.score_breakdown,
                "match_confidence": s.match_confidence,
            }
            for s in scores
        ],
    })


@bp.get("/api/source-health")
@roles_required(UserRole.ADMIN)
def source_health():
    report = db.session.query(TrendReport).order_by(TrendReport.report_date.desc()).first()
    if not report:
        return jsonify({"found": False, "records": []})

    records = (
        db.session.query(SourceHealthRecord)
        .filter(SourceHealthRecord.report_id == report.id)
        .order_by(SourceHealthRecord.source)
        .all()
    )

    return jsonify({
        "found": True,
        "report_id": report.id,
        "records": [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "keyword": r.keyword,
                "item_count": r.item_count,
                "error_message": r.error_message,
                "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            }
            for r in records
        ],
    })


@bp.post("/actions/print-now")
@roles_required(UserRole.ADMIN)
def action_print_now():
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "")
    if not product_id:
        record_audit_event(
            action="trend_scout.print_now.skipped",
            entity_type="trend_opportunity",
            entity_id=keyword or "unknown",
            metadata={"reason": "no_product_id", "keyword": keyword},
            source_module=__name__,
        )
        return '<span class="text-xs" style="color:var(--color-text-muted);">No product</span>'

    product = db.session.get(Product, product_id)
    if not product:
        return '<span class="text-xs" style="color:var(--color-danger);">Not found</span>'

    job = PrintJob(
        product_id=product.id,
        status=PrintJobStatus.QUEUED,
        priority=1,
        estimated_minutes=product.parsed_print_minutes or product.estimated_print_minutes or 0,
        label=f"Trend Scout: {product.name}",
    )
    db.session.add(job)
    db.session.commit()

    record_audit_event(
        action="trend_scout.print_now.created",
        entity_type="print_job",
        entity_id=job.id,
        metadata={
            "product_id": product_id,
            "product_name": product.name,
            "keyword": keyword,
            "source": "trend_scout",
        },
        source_module=__name__,
    )

    return (
        f'<span class="text-xs" style="color:var(--color-success);">'
        f'Queued #{job.id}</span>'
    )


@bp.post("/actions/create-product")
@roles_required(UserRole.ADMIN)
def action_create_product():
    keyword = request.form.get("keyword", "").strip()
    title = request.form.get("title", "").strip() or keyword
    if not keyword:
        return '<span class="text-xs" style="color:var(--color-danger);">No keyword</span>'

    record_audit_event(
        action="trend_scout.create_product.redirected",
        entity_type="trend_opportunity",
        entity_id=keyword,
        metadata={"keyword": keyword, "title": title, "source": "trend_scout"},
        source_module=__name__,
    )

    return redirect(url_for("products.studio", mode="create", name=title))


@bp.post("/actions/flag-clearance")
@roles_required(UserRole.ADMIN)
def action_flag_clearance():
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "")
    if not product_id:
        return '<span class="text-xs" style="color:var(--color-text-muted);">No product</span>'

    product = db.session.get(Product, product_id)
    if not product:
        return '<span class="text-xs" style="color:var(--color-danger);">Not found</span>'

    existing = (product.admin_notes or "") + (
        f"\n[Trend Scout - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}] "
        f"Flagged for clearance review."
    )
    product.admin_notes = existing.strip()
    db.session.add(product)
    db.session.commit()

    record_audit_event(
        action="trend_scout.flag_clearance",
        entity_type="product",
        entity_id=product_id,
        metadata={"product_name": product.name, "keyword": keyword, "source": "trend_scout"},
        source_module=__name__,
    )

    return '<span class="text-xs" style="color:var(--color-warning);">Flagged clearance</span>'


@bp.post("/actions/flag-retire")
@roles_required(UserRole.ADMIN)
def action_flag_retire():
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "")
    if not product_id:
        return '<span class="text-xs" style="color:var(--color-text-muted);">No product</span>'

    product = db.session.get(Product, product_id)
    if not product:
        return '<span class="text-xs" style="color:var(--color-danger);">Not found</span>'

    existing = (product.admin_notes or "") + (
        f"\n[Trend Scout - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}] "
        f"Flagged for retirement review."
    )
    product.admin_notes = existing.strip()
    db.session.add(product)
    db.session.commit()

    record_audit_event(
        action="trend_scout.flag_retire",
        entity_type="product",
        entity_id=product_id,
        metadata={"product_name": product.name, "keyword": keyword, "source": "trend_scout"},
        source_module=__name__,
    )

    return '<span class="text-xs" style="color:var(--color-danger);">Flagged retire</span>'


@bp.post("/actions/flag-license-review")
@roles_required(UserRole.ADMIN)
def action_flag_license_review():
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "")
    if not product_id:
        return '<span class="text-xs" style="color:var(--color-text-muted);">No product</span>'

    product = db.session.get(Product, product_id)
    if not product:
        return '<span class="text-xs" style="color:var(--color-danger);">Not found</span>'

    existing = (product.admin_notes or "") + (
        f"\n[Trend Scout - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}] "
        f"Flagged for license review."
    )
    product.admin_notes = existing.strip()
    db.session.add(product)
    db.session.commit()

    record_audit_event(
        action="trend_scout.flag_license_review",
        entity_type="product",
        entity_id=product_id,
        metadata={"product_name": product.name, "keyword": keyword, "source": "trend_scout"},
        source_module=__name__,
    )

    return '<span class="text-xs" style="color:var(--color-warning);">Flagged license</span>'


@bp.get("/monitor")
@roles_required(UserRole.ADMIN)
def task_monitor():
    from app.services.trend_scout_task_monitor import get_recent_task_runs

    runs = get_recent_task_runs(limit=100)
    return render_template("trend_scout/monitor.html", runs=runs)


@bp.get("/monitor/<run_id>")
@roles_required(UserRole.ADMIN)
def task_monitor_detail(run_id: str):
    from app.services.trend_scout_task_monitor import get_task_run
    from app.models import TrendReport

    run = get_task_run(run_id)
    if not run:
        abort(404)
    report = None
    if run.report_id:
        report = db.session.get(TrendReport, run.report_id)
    return render_template("trend_scout/monitor_detail.html", run=run, report=report)


@bp.post("/monitor/<run_id>/cancel")
@roles_required(UserRole.ADMIN)
def task_monitor_cancel(run_id: str):
    from app.services.trend_scout_task_monitor import cancel_task_run, get_task_run

    run = get_task_run(run_id)
    if not run:
        return jsonify({"error": "not_found"}), 404
    if run.status not in ("pending", "running"):
        return jsonify({"error": f"Cannot cancel task with status '{run.status}'"}), 400
    if run.celery_task_id:
        celery.control.revoke(run.celery_task_id, terminate=True)
    cancel_task_run(run_id)
    record_audit_event(
        action="trend_scout.task_cancelled",
        entity_type="trend_task_run",
        entity_id=run_id,
        metadata={"celery_task_id": run.celery_task_id, "trigger": run.trigger},
        source_module=__name__,
    )
    return jsonify({"status": "cancelled"})


@bp.post("/monitor/<run_id>/retry")
@roles_required(UserRole.ADMIN)
def task_monitor_retry(run_id: str):
    from app.services.trend_scout_task_monitor import get_task_run

    run = get_task_run(run_id)
    if not run:
        return jsonify({"error": "not_found"}), 404
    if run.status != "failed":
        return jsonify({"error": f"Can only retry failed tasks, status is '{run.status}'"}), 400

    from app.tasks.trend_scout import trend_scout_pipeline

    task = trend_scout_pipeline.delay()
    session["trend_scout_task_id"] = task.id
    record_audit_event(
        action="trend_scout.task_retried",
        entity_type="trend_task_run",
        entity_id=run_id,
        metadata={"new_celery_task_id": task.id, "trigger": run.trigger},
        source_module=__name__,
    )
    return jsonify({"task_id": task.id, "status": "dispatched"})


@bp.get("/backtest")
@roles_required(UserRole.ADMIN)
def backtest():
    from app.services.trend_scout_backtest import run_backtest

    lookback = request.args.get("lookback", 12, type=int)
    window = request.args.get("window", 60, type=int)
    result = run_backtest(db.session, lookback_reports=lookback, sales_window_days=window)
    return render_template("trend_scout/backtest.html", result=result)
