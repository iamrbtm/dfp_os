from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone

from flask import abort, jsonify, redirect, render_template, request, Response, session, url_for

from app.blueprints.trend_scout import bp
from app.celery_app import celery
from app.extensions import db
from app.models import (
    Market,
    MarketPackingList,
    MarketStatus,
    PrepTask,
    PrepTaskCategory,
    PrintJob,
    PrintJobStatus,
    Product,
    SourceHealthRecord,
    TrendOpportunityScore,
    TrendReport,
    UserRole,
)
from app.services.audit import record_audit_event
from app.services.trend_scout_weights import (
    DEFAULT_SCORE_WEIGHTS,
    DEFAULT_SOURCE_WEIGHTS,
    DEFAULT_BUYER_SOURCE_WEIGHTS,
    DEFAULT_METRIC_WEIGHTS,
    PREFIX_SCORE,
    PREFIX_SOURCE,
    PREFIX_BUYER,
    PREFIX_METRIC,
    load_all_weights,
    load_score_weights,
    load_source_weights,
    validate_score_weights,
    save_weight,
)
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
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    scores_pagination = None
    if latest:
        source_health = (
            db.session.query(SourceHealthRecord)
            .filter(SourceHealthRecord.report_id == latest.id)
            .order_by(SourceHealthRecord.source)
            .all()
        )
        scores_query = (
            db.session.query(TrendOpportunityScore)
            .filter(
                TrendOpportunityScore.report_id == latest.id,
                TrendOpportunityScore.dismissed == False,
            )
            .order_by(TrendOpportunityScore.rank.asc().nulls_last(), TrendOpportunityScore.opportunity_score.desc())
        )
        scores_pagination = db.paginate(scores_query, page=page, per_page=per_page, error_out=False)

    provider_setup = _provider_setup_status()
    return render_template(
        "trend_scout/index.html",
        latest=latest,
        all_reports=all_reports,
        source_health=source_health,
        provider_setup=provider_setup,
        scores_pagination=scores_pagination,
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
                "dismissed": s.dismissed,
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


@bp.get("/api/reports/<int:report_id>/scores")
@roles_required(UserRole.ADMIN)
def api_report_scores(report_id: int):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    action_filter = request.args.get("action")
    include_dismissed = request.args.get("include_dismissed", "0") == "1"

    report = db.session.get(TrendReport, report_id)
    if not report:
        return jsonify({"found": False}), 404

    query = db.session.query(TrendOpportunityScore).filter(
        TrendOpportunityScore.report_id == report_id,
    )
    if not include_dismissed:
        query = query.filter(TrendOpportunityScore.dismissed == False)
    if action_filter:
        query = query.filter(TrendOpportunityScore.action == action_filter)

    query = query.order_by(
        TrendOpportunityScore.rank.asc().nulls_last(),
        TrendOpportunityScore.opportunity_score.desc(),
    )
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

    return jsonify({
        "found": True,
        "report_id": report.id,
        "report_date": report.report_date.isoformat(),
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
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
                "dismissed": s.dismissed,
            }
            for s in pagination.items
        ],
    })


@bp.get("/api/score-history")
@roles_required(UserRole.ADMIN)
def api_score_history():
    from app.services.trend_scout_history import get_score_history

    keyword = request.args.get("keyword")
    limit = request.args.get("limit", 20, type=int)
    history = get_score_history(keyword=keyword, limit=limit)
    return jsonify({"history": history})


@bp.get("/api/biggest-movers")
@roles_required(UserRole.ADMIN)
def api_biggest_movers():
    from app.services.trend_scout_history import get_biggest_movers

    top_n = request.args.get("top_n", 10, type=int)
    movers = get_biggest_movers(top_n=top_n)
    return jsonify({"movers": movers})


@bp.get("/score-history/<string:keyword>")
@roles_required(UserRole.ADMIN)
def score_history_page(keyword: str):
    from app.services.trend_scout_history import get_score_history

    history = get_score_history(keyword=keyword, limit=50)
    return render_template(
        "trend_scout/score_history.html",
        keyword=keyword,
        history=history,
    )


@bp.post("/api/opportunities/<int:score_id>/dismiss")
@roles_required(UserRole.ADMIN)
def api_dismiss_opportunity(score_id: int):
    score = db.session.get(TrendOpportunityScore, score_id)
    if not score:
        return jsonify({"error": "not_found"}), 404
    score.dismissed = True
    score.dismissed_at = datetime.now(timezone.utc)
    db.session.commit()
    record_audit_event(
        action="trend_scout.opportunity.dismissed",
        entity_type="trend_opportunity_score",
        entity_id=str(score_id),
        metadata={"keyword": score.keyword, "report_id": score.report_id},
        source_module=__name__,
    )
    return jsonify({"status": "dismissed"})


@bp.post("/api/opportunities/<int:score_id>/undo-dismiss")
@roles_required(UserRole.ADMIN)
def api_undo_dismiss(score_id: int):
    score = db.session.get(TrendOpportunityScore, score_id)
    if not score:
        return jsonify({"error": "not_found"}), 404
    score.dismissed = False
    score.dismissed_at = None
    db.session.commit()
    record_audit_event(
        action="trend_scout.opportunity.undismissed",
        entity_type="trend_opportunity_score",
        entity_id=str(score_id),
        metadata={"keyword": score.keyword, "report_id": score.report_id},
        source_module=__name__,
    )
    return jsonify({"status": "undismissed"})


# -- Phase 8: Dedicated Settings Page --

def _profile_storage_key(name: str) -> str:
    return f"trend_profile.{name}"


def _list_profiles() -> list[str]:
    from app.models import Setting
    records = (
        db.session.query(Setting)
        .filter(Setting.key.startswith("trend_profile."))
        .all()
    )
    return [r.key.replace("trend_profile.", "") for r in records]


def _load_profile(name: str) -> dict | None:
    from app.models import Setting
    import json
    record = db.session.query(Setting).filter(
        Setting.key == _profile_storage_key(name)
    ).first()
    if record and record.value:
        try:
            return json.loads(record.value)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


@bp.route("/settings", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN)
def settings():
    from app.models import Setting

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_weights":
            weight_type = request.form.get("weight_type", "score")
            prefix_map = {
                "score": (PREFIX_SCORE, DEFAULT_SCORE_WEIGHTS),
                "source": (PREFIX_SOURCE, DEFAULT_SOURCE_WEIGHTS),
                "buyer": (PREFIX_BUYER, DEFAULT_BUYER_SOURCE_WEIGHTS),
                "metric": (PREFIX_METRIC, DEFAULT_METRIC_WEIGHTS),
            }
            prefix, defaults = prefix_map.get(weight_type, (PREFIX_SCORE, DEFAULT_SCORE_WEIGHTS))
            for key in defaults:
                val = request.form.get(f"weight_{key}")
                if val is not None:
                    try:
                        save_weight(prefix, key, float(val))
                    except (ValueError, TypeError):
                        pass
            record_audit_event(
                action="trend_scout.settings.weights_saved",
                entity_type="settings",
                entity_id=f"weights_{weight_type}",
                metadata={"weight_type": weight_type},
                source_module=__name__,
            )

        elif action == "save_profile":
            profile_name = request.form.get("profile_name", "").strip()
            if profile_name:
                import json
                weights = load_all_weights()
                existing = db.session.query(Setting).filter(
                    Setting.key == _profile_storage_key(profile_name)
                ).first()
                if existing:
                    existing.value = json.dumps(weights)
                else:
                    db.session.add(Setting(
                        key=_profile_storage_key(profile_name),
                        value=json.dumps(weights),
                        description=f"Trend Scout profile: {profile_name}",
                        type="json",
                    ))
                db.session.commit()
                record_audit_event(
                    action="trend_scout.settings.profile_saved",
                    entity_type="settings",
                    entity_id=f"profile_{profile_name}",
                    metadata={"profile": profile_name},
                    source_module=__name__,
                )

        elif action == "load_profile":
            profile_name = request.form.get("profile_name", "").strip()
            if profile_name:
                profile = _load_profile(profile_name)
                if profile:
                    for group_key in ("score_weights", "source_weights", "buyer_source_weights", "metric_weights"):
                        prefix_map = {
                            "score_weights": PREFIX_SCORE,
                            "source_weights": PREFIX_SOURCE,
                            "buyer_source_weights": PREFIX_BUYER,
                            "metric_weights": PREFIX_METRIC,
                        }
                        prefix = prefix_map.get(group_key)
                        if prefix and group_key in profile:
                            for key, val in profile[group_key].items():
                                save_weight(prefix, key, float(val))
                    record_audit_event(
                        action="trend_scout.settings.profile_loaded",
                        entity_type="settings",
                        entity_id=f"profile_{profile_name}",
                        metadata={"profile": profile_name},
                        source_module=__name__,
                    )

        elif action == "delete_profile":
            profile_name = request.form.get("profile_name", "").strip()
            if profile_name:
                db.session.query(Setting).filter(
                    Setting.key == _profile_storage_key(profile_name)
                ).delete()
                db.session.commit()

        elif action == "toggle_source":
            source_key = request.form.get("source_key", "")
            enabled = request.form.get("enabled", "1") == "1"
            if source_key:
                setting_key = f"trend_source_enabled.{source_key}"
                existing = db.session.query(Setting).filter(
                    Setting.key == setting_key
                ).first()
                if existing:
                    existing.value = "1" if enabled else "0"
                else:
                    db.session.add(Setting(
                        key=setting_key,
                        value="1" if enabled else "0",
                        description=f"Trend Scout source enabled: {source_key}",
                        type="boolean",
                    ))
                db.session.commit()
                record_audit_event(
                    action="trend_scout.settings.source_toggled",
                    entity_type="settings",
                    entity_id=f"source_{source_key}",
                    metadata={"source": source_key, "enabled": enabled},
                    source_module=__name__,
                )

        return redirect(url_for("trend_scout.settings"))

    weights = load_all_weights()
    profiles = _list_profiles()
    source_keys = list(DEFAULT_SOURCE_WEIGHTS)

    source_enabled_state: dict[str, bool] = {}
    for sk in source_keys:
        setting = db.session.query(Setting).filter(
            Setting.key == f"trend_source_enabled.{sk}"
        ).first()
        source_enabled_state[sk] = setting is None or setting.value == "1"

    return render_template(
        "trend_scout/settings.html",
        weights=weights,
        profiles=profiles,
        source_keys=source_keys,
        source_enabled_state=source_enabled_state,
        DEFAULT_SCORE_WEIGHTS=DEFAULT_SCORE_WEIGHTS,
        DEFAULT_SOURCE_WEIGHTS=DEFAULT_SOURCE_WEIGHTS,
    )


# -- Phase 9: Report Detail & Comparison --

@bp.get("/reports/<int:report_id>")
@roles_required(UserRole.ADMIN)
def report_detail(report_id: int):
    report = db.session.get(TrendReport, report_id)
    if not report:
        abort(404)

    compare_id = request.args.get("compare", type=int)
    compare_report = None
    if compare_id:
        compare_report = db.session.get(TrendReport, compare_id)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    action_filter = request.args.get("action")

    query = db.session.query(TrendOpportunityScore).filter(
        TrendOpportunityScore.report_id == report_id,
        TrendOpportunityScore.dismissed == False,
    )
    if action_filter:
        query = query.filter(TrendOpportunityScore.action == action_filter)

    query = query.order_by(
        TrendOpportunityScore.rank.asc().nulls_last(),
        TrendOpportunityScore.opportunity_score.desc(),
    )
    scores_pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

    compare_scores = None
    if compare_report:
        cq = db.session.query(TrendOpportunityScore).filter(
            TrendOpportunityScore.report_id == compare_report.id,
            TrendOpportunityScore.dismissed == False,
        )
        if action_filter:
            cq = cq.filter(TrendOpportunityScore.action == action_filter)
        compare_scores = {
            s.keyword: s.opportunity_score
            for s in cq.order_by(TrendOpportunityScore.keyword).all()
        }

    source_health = (
        db.session.query(SourceHealthRecord)
        .filter(SourceHealthRecord.report_id == report.id)
        .order_by(SourceHealthRecord.source)
        .all()
    )

    all_reports = (
        db.session.query(TrendReport)
        .order_by(TrendReport.report_date.desc())
        .limit(100)
        .all()
    )

    return render_template(
        "trend_scout/report_detail.html",
        report=report,
        compare_report=compare_report,
        compare_scores=compare_scores,
        scores_pagination=scores_pagination,
        source_health=source_health,
        all_reports=all_reports,
    )


@bp.get("/reports/<int:report_id>/csv")
@roles_required(UserRole.ADMIN)
def report_csv(report_id: int):
    report = db.session.get(TrendReport, report_id)
    if not report:
        abort(404)

    scores = (
        db.session.query(TrendOpportunityScore)
        .filter(
            TrendOpportunityScore.report_id == report_id,
            TrendOpportunityScore.dismissed == False,
        )
        .order_by(TrendOpportunityScore.rank.asc().nulls_last())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "rank", "keyword", "title", "candidate_type", "action",
        "opportunity_score", "purchase_intent", "trend_velocity",
        "price_resilience", "low_saturation", "local_fit",
        "production_fit", "license_risk", "inventory_available",
        "base_price", "license_status", "match_confidence", "sources",
    ])
    for s in scores:
        writer.writerow([
            s.rank, s.keyword, s.title, s.candidate_type, s.action,
            s.opportunity_score, s.purchase_intent, s.trend_velocity,
            s.price_resilience, s.low_saturation, s.local_fit,
            s.production_fit, s.license_risk, s.inventory_available,
            str(s.base_price), s.license_status or "",
            s.match_confidence or "",
            ", ".join(s.sources) if s.sources else "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=trend_report_{report_id}.csv"},
    )


@bp.get("/reports/<int:report_id>/export.csv")
@roles_required(UserRole.ADMIN)
def report_csv_alt(report_id: int):
    return report_csv(report_id)


@bp.post("/actions/print-now")
@roles_required(UserRole.ADMIN)
def action_print_now():
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "")
    trend_opportunity_id = request.form.get("trend_opportunity_id", type=int)
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
        trend_opportunity_id=trend_opportunity_id,
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
            "trend_opportunity_id": trend_opportunity_id,
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


# -- Phase 11: Calibration History & Comparison --

@bp.get("/calibration")
@roles_required(UserRole.ADMIN)
def calibration():
    from app.services.trend_scout_calibration import get_calibration_history, run_and_store_calibration

    if request.args.get("run") == "1":
        result = run_and_store_calibration(trigger="manual")
        record_audit_event(
            action="trend_scout.calibration.manual_run",
            entity_type="trend_calibration_result",
            entity_id=str(result.id),
            metadata={
                "mae": result.mae,
                "precision": result.precision_at_high_score,
                "report_count": result.report_count,
            },
            source_module=__name__,
        )
        return redirect(url_for("trend_scout.calibration"))

    history = get_calibration_history(limit=20)
    comparison = None
    regression = None
    if len(history) >= 2:
        prev, curr = history[1], history[0]
        comparison = {
            "prev_date": prev.run_date,
            "curr_date": curr.run_date,
            "mae_change": (curr.mae - prev.mae) if (curr.mae is not None and prev.mae is not None) else None,
            "precision_change": (
                (curr.precision_at_high_score - prev.precision_at_high_score)
                if (curr.precision_at_high_score is not None and prev.precision_at_high_score is not None)
                else None
            ),
            "f1_change": (curr.f1_score - prev.f1_score) if (curr.f1_score is not None and prev.f1_score is not None) else None,
            "prev": prev,
            "curr": curr,
        }
        from app.services.trend_scout_calibration import check_regression as _check_regression
        regression = _check_regression()

    return render_template(
        "trend_scout/calibration.html",
        history=history,
        comparison=comparison,
        regression=regression,
    )


@bp.get("/calibration/<int:cal_id>")
@roles_required(UserRole.ADMIN)
def calibration_detail(cal_id: int):
    from app.models.trend import TrendCalibrationResult

    cal = db.session.get(TrendCalibrationResult, cal_id)
    if not cal:
        abort(404)
    return render_template("trend_scout/calibration_detail.html", cal=cal)


# -- Phase 13: Market Prep Integration --

@bp.route("/actions/add-to-market-prep", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN)
def action_add_to_market_prep():
    if request.method == "GET":
        upcoming_markets = (
            db.session.query(Market)
            .filter(
                Market.status.in_([MarketStatus.ACCEPTED, MarketStatus.SCHEDULED]),
                Market.event_date.isnot(None),
            )
            .order_by(Market.event_date.asc())
            .all()
        )
        product_id = request.args.get("product_id", type=int)
        keyword = request.args.get("keyword", "")
        score = request.args.get("score", type=int)
        return render_template(
            "trend_scout/add_to_market_prep.html",
            upcoming_markets=upcoming_markets,
            product_id=product_id,
            keyword=keyword,
            score=score,
        )

    market_id = request.form.get("market_id", type=int)
    product_id = request.form.get("product_id", type=int)
    keyword = request.form.get("keyword", "").strip()
    score = request.form.get("score", type=int)

    if not market_id or not product_id:
        return jsonify({"error": "market_id and product_id required"}), 400

    market = db.session.get(Market, market_id)
    if not market:
        return jsonify({"error": "market not found"}), 404
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "product not found"}), 404

    suggested_qty = 3
    if score:
        suggested_qty = max(1, round(score / 20))

    existing = (
        db.session.query(MarketPackingList)
        .filter(
            MarketPackingList.market_id == market_id,
            MarketPackingList.product_id == product_id,
        )
        .first()
    )
    if existing:
        existing.planned_quantity = (existing.planned_quantity or 0) + suggested_qty
        packing = existing
    else:
        packing = MarketPackingList(
            market_id=market_id,
            product_id=product_id,
            planned_quantity=suggested_qty,
            notes=f"Trend Scout suggestion: {keyword}",
        )
        db.session.add(packing)
    db.session.commit()

    reprint_task = PrepTask(
        market_id=market_id,
        title=f"Print {suggested_qty} x {product.name}",
        category=PrepTaskCategory.REPRINT,
        status="open",
        source="trend_scout",
        notes=f"Suggested by Trend Scout for market '{market.name}'. Score: {score}. Keyword: {keyword}.",
    )
    db.session.add(reprint_task)
    db.session.commit()

    record_audit_event(
        action="trend_scout.added_to_market_prep",
        entity_type="market_packing_list",
        entity_id=packing.id,
        metadata={
            "market_id": market_id,
            "market_name": market.name,
            "product_id": product_id,
            "product_name": product.name,
            "keyword": keyword,
            "score": score,
            "suggested_qty": suggested_qty,
            "reprint_task_id": reprint_task.id,
        },
        source_module=__name__,
    )

    return redirect(url_for("trend_scout.index"))


@bp.get("/backtest")
@roles_required(UserRole.ADMIN)
def backtest():
    from app.services.trend_scout_backtest import run_backtest

    lookback = request.args.get("lookback", 12, type=int)
    window = request.args.get("window", 60, type=int)
    result = run_backtest(db.session, lookback_reports=lookback, sales_window_days=window)
    return render_template("trend_scout/backtest.html", result=result)
