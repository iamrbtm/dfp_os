from __future__ import annotations

import csv
import io
import os
from math import ceil
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
    Setting,
    UserRole,
)
from app.services.audit import record_audit_event
from app.services.trend_scout_proxy import TrendScoutUnavailable, get_trend_scout_proxy
from app.utils.auth import roles_required


class AttrDict(dict):
    """Dict with attribute access for existing Jinja templates."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class ProxyPagination:
    def __init__(self, items: list[dict], page: int, per_page: int, total: int):
        self.items = [_objectify(item) for item in items]
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(1, ceil(total / per_page)) if per_page else 1


def _parse_dt(value):
    if not value or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _objectify(value):
    if isinstance(value, dict):
        out = AttrDict()
        for key, item in value.items():
            out[key] = _objectify(item)
        for key in ("report_date", "created_at", "scraped_at", "run_date"):
            if key in out:
                out[key] = _parse_dt(out[key])
        return out
    if isinstance(value, list):
        return [_objectify(item) for item in value]
    return value


def _json_error(exc: Exception, status_code: int = 503):
    return jsonify({"error": "trend_scout_unavailable", "message": str(exc)}), status_code


def _pagination_from_response(payload: dict, page: int, per_page: int) -> ProxyPagination:
    return ProxyPagination(
        payload.get("items", []),
        page=page,
        per_page=per_page,
        total=int(payload.get("total") or 0),
    )

_PROVIDER_CONFIG_CHECKS: dict[str, list[tuple[str, str]]] = {
    "etsy": [("ETSY_API_KEY", "API key")],
    "google_trends": [("SERPAPI_API_KEY", "SerpAPI key")],
    "tiktok": [("TIKTOK_RESEARCH_ACCESS_TOKEN", "Research API token")],
    "pinterest": [("PINTEREST_API_KEY", "API key")],
    "last30days": [("LAST30DAYS_RAW_FILE", "raw file path")],
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


def _latest_report_and_reports(proxy):
    latest_payload = proxy.latest_report()
    latest = _objectify(latest_payload) if latest_payload else None
    all_reports = _objectify(proxy.list_reports(limit=20).get("items", []))
    return latest, all_reports


@bp.get("/")
@roles_required(UserRole.ADMIN)
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    try:
        proxy = get_trend_scout_proxy()
        latest, all_reports = _latest_report_and_reports(proxy)
        source_health = _objectify(proxy.source_health(limit=100).get("items", [])) if latest else []
        scores_pagination = None
        if latest:
            scores_pagination = _pagination_from_response(
                proxy.report_opportunities(latest.id, page=page, per_page=per_page),
                page,
                per_page,
            )
    except TrendScoutUnavailable as exc:
        return (
            render_template(
                "trend_scout/index.html",
                latest=None,
                all_reports=[],
                source_health=[],
                provider_setup=_provider_setup_status(),
                scores_pagination=None,
                freshness_label=_freshness_label,
                freshness_score=_freshness_score,
                service_error=str(exc),
            ),
            503,
        )

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
    report = get_trend_scout_proxy().latest_report()
    if not report:
        return jsonify({"found": False})
    report["found"] = True
    return jsonify(report)


@bp.post("/run")
@roles_required(UserRole.ADMIN)
def run_pipeline():
    try:
        payload = get_trend_scout_proxy().run_pipeline(trigger="manual")
    except TrendScoutUnavailable as exc:
        return _json_error(exc)
    session["trend_scout_task_id"] = payload.get("run_id") or payload.get("task_id")
    return jsonify({"task_id": payload.get("task_id"), "run_id": payload.get("run_id"), "status": payload.get("status", "queued")})


@bp.get("/run/status/<task_id>")
@roles_required(UserRole.ADMIN)
def run_status(task_id: str):
    try:
        return jsonify(get_trend_scout_proxy().pipeline_status(task_id))
    except TrendScoutUnavailable as exc:
        return _json_error(exc)


@bp.get("/pipeline/progress")
@roles_required(UserRole.ADMIN)
def pipeline_progress():
    task_id = session.get("trend_scout_task_id")
    if not task_id:
        return '<div id="pipeline-progress" class="hidden"></div>'
    try:
        payload = get_trend_scout_proxy().pipeline_status(task_id)
    except TrendScoutUnavailable:
        return '<div id="pipeline-progress" class="hidden"></div>'
    state = payload.get("state", "unknown")
    if state in ("success", "failed", "unknown"):
        session.pop("trend_scout_task_id", None)
        return '<div id="pipeline-progress" class="hidden"></div>'
    percent = int(payload.get("progress") or 0)

    return render_template(
        "trend_scout/_pipeline_progress.html",
        current=percent,
        total=100,
        percent=percent,
        step=payload.get("completed_step") or "Trend Scout pipeline running",
        status=state,
        task_running=True,
    )


@bp.get("/api/reports")
@roles_required(UserRole.ADMIN)
def report_list():
    reports = get_trend_scout_proxy().list_reports(limit=50).get("items", [])
    return jsonify(
        [
            {
                "id": r.get("id"),
                "report_date": r.get("report_date"),
                "summary": (r.get("summary") or "")[:200],
                "opportunity_count": len(r.get("top_opportunities") or []),
                "growing_count": len(r.get("growing_categories") or []),
            }
            for r in reports
        ]
    )


@bp.get("/api/persisted-scores")
@roles_required(UserRole.ADMIN)
def persisted_scores():
    proxy = get_trend_scout_proxy()
    report = proxy.latest_report()
    if not report:
        return jsonify({"found": False, "scores": []})
    scores = proxy.list_opportunities(report_id=report["id"], include_dismissed=False, limit=200).get("items", [])

    return jsonify(
        {
            "found": True,
            "report_id": report["id"],
            "report_date": report.get("report_date"),
            "scores": scores,
        }
    )


@bp.get("/api/source-health")
@roles_required(UserRole.ADMIN)
def source_health():
    proxy = get_trend_scout_proxy()
    report = proxy.latest_report()
    if not report:
        return jsonify({"found": False, "records": []})
    records = proxy.source_health(limit=200).get("items", [])

    return jsonify(
        {
            "found": True,
            "report_id": report["id"],
            "records": records,
        }
    )


@bp.get("/api/reports/<int:report_id>/scores")
@roles_required(UserRole.ADMIN)
def api_report_scores(report_id: int):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    action_filter = request.args.get("action")
    include_dismissed = request.args.get("include_dismissed", "0") == "1"

    proxy = get_trend_scout_proxy()
    try:
        report = proxy.report_by_id(report_id)
    except TrendScoutUnavailable as exc:
        return _json_error(exc, 404)
    payload = proxy.report_opportunities(
        report_id,
        action=action_filter,
        include_dismissed=include_dismissed,
        page=page,
        per_page=per_page,
    )
    pagination = _pagination_from_response(payload, page, per_page)

    return jsonify(
        {
            "found": True,
            "report_id": report["id"],
            "report_date": report.get("report_date"),
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "scores": pagination.items,
        }
    )


@bp.get("/api/score-history")
@roles_required(UserRole.ADMIN)
def api_score_history():
    keyword = request.args.get("keyword")
    limit = request.args.get("limit", 20, type=int)
    proxy = get_trend_scout_proxy()
    history = []
    for report in proxy.list_reports(limit=limit).get("items", []):
        items = proxy.list_opportunities(report_id=report["id"], include_dismissed=True, limit=200).get("items", [])
        for item in items:
            if keyword and item.get("keyword") != keyword:
                continue
            history.append(
                {
                    "report_id": report["id"],
                    "report_date": report.get("report_date"),
                    "keyword": item.get("keyword"),
                    "opportunity_score": item.get("opportunity_score"),
                    "action": item.get("action"),
                }
            )
    return jsonify({"history": history})


@bp.get("/api/biggest-movers")
@roles_required(UserRole.ADMIN)
def api_biggest_movers():
    top_n = request.args.get("top_n", 10, type=int)
    proxy = get_trend_scout_proxy()
    reports = proxy.list_reports(limit=2).get("items", [])
    movers = []
    if len(reports) >= 2:
        latest, previous = reports[0], reports[1]
        current = {
            item["keyword"]: item
            for item in proxy.list_opportunities(report_id=latest["id"], include_dismissed=True, limit=200).get("items", [])
        }
        prior = {
            item["keyword"]: item
            for item in proxy.list_opportunities(report_id=previous["id"], include_dismissed=True, limit=200).get("items", [])
        }
        for keyword, item in current.items():
            old = prior.get(keyword)
            if not old:
                continue
            movers.append(
                {
                    "keyword": keyword,
                    "current_score": item.get("opportunity_score", 0),
                    "previous_score": old.get("opportunity_score", 0),
                    "delta": item.get("opportunity_score", 0) - old.get("opportunity_score", 0),
                }
            )
        movers = sorted(movers, key=lambda row: abs(row["delta"]), reverse=True)[:top_n]
    return jsonify({"movers": movers})


@bp.get("/score-history/<string:keyword>")
@roles_required(UserRole.ADMIN)
def score_history_page(keyword: str):
    proxy = get_trend_scout_proxy()
    history = []
    for report in proxy.list_reports(limit=50).get("items", []):
        items = proxy.list_opportunities(report_id=report["id"], include_dismissed=True, limit=200).get("items", [])
        for item in items:
            if item.get("keyword") == keyword:
                history.append(
                    _objectify(
                        {
                            "report_id": report["id"],
                            "report_date": report.get("report_date"),
                            "keyword": keyword,
                            "opportunity_score": item.get("opportunity_score"),
                            "action": item.get("action"),
                        }
                    )
                )
    return render_template(
        "trend_scout/score_history.html",
        keyword=keyword,
        history=history,
    )


@bp.post("/api/opportunities/<int:score_id>/dismiss")
@roles_required(UserRole.ADMIN)
def api_dismiss_opportunity(score_id: int):
    try:
        score = get_trend_scout_proxy().dismiss_opportunity(score_id)
    except TrendScoutUnavailable as exc:
        return _json_error(exc, 404)
    record_audit_event(
        action="trend_scout.opportunity.dismissed",
        entity_type="trend_opportunity_score",
        entity_id=str(score_id),
        metadata={"keyword": score.get("keyword"), "report_id": score.get("report_id")},
        source_module=__name__,
    )
    return jsonify({"status": "dismissed"})


@bp.post("/api/opportunities/<int:score_id>/undo-dismiss")
@roles_required(UserRole.ADMIN)
def api_undo_dismiss(score_id: int):
    try:
        score = get_trend_scout_proxy().undismiss_opportunity(score_id)
    except TrendScoutUnavailable as exc:
        return _json_error(exc, 404)
    record_audit_event(
        action="trend_scout.opportunity.undismissed",
        entity_type="trend_opportunity_score",
        entity_id=str(score_id),
        metadata={"keyword": score.get("keyword"), "report_id": score.get("report_id")},
        source_module=__name__,
    )
    return jsonify({"status": "undismissed"})


# -- Phase 8: Dedicated Settings Page --


def _profile_storage_key(name: str) -> str:
    return f"trend_profile.{name}"


def _list_profiles() -> list[str]:
    records = db.session.query(Setting).filter(Setting.key.startswith("trend_profile.")).all()
    return [r.key.replace("trend_profile.", "") for r in records]


def _load_profile(name: str) -> dict | None:
    import json

    record = db.session.query(Setting).filter(Setting.key == _profile_storage_key(name)).first()
    if record and record.value:
        try:
            return json.loads(record.value)
        except json.JSONDecodeError, TypeError:
            return None
    return None


def _weights_from_proxy(proxy) -> dict:
    defaults = proxy.weight_defaults()
    weights = {
        "score_weights": dict(defaults.get("score", {})),
        "source_weights": dict(defaults.get("source", {})),
        "buyer_source_weights": dict(defaults.get("buyer", {})),
        "metric_weights": dict(defaults.get("metric", {})),
    }
    for entry in proxy.list_weights(limit=500).get("items", []):
        group = entry.get("group")
        key = entry.get("key")
        if not key:
            continue
        target = {
            "score": "score_weights",
            "source": "source_weights",
            "buyer": "buyer_source_weights",
            "metric": "metric_weights",
        }.get(group)
        if target:
            weights[target][key] = float(entry.get("value", 0))
    return weights


def _calibration_view_model(row: dict) -> AttrDict:
    summary = row.get("summary") or {}
    return _objectify(
        {
            "id": row.get("id") or abs(hash(row.get("_group", row.get("run_date", "")))) % 10_000_000,
            "run_date": row.get("run_date"),
            "trigger": row.get("trigger", "manual"),
            "report_count": row.get("report_count", 0),
            "score_count": summary.get("score_count", 0),
            "mae": summary.get("mae"),
            "rmse": summary.get("rmse"),
            "precision_at_high_score": summary.get("precision_at_high_score")
            or summary.get("top_hit_rate"),
            "recall_of_sellers": summary.get("recall_of_sellers"),
            "f1_score": summary.get("f1") or summary.get("f1_score"),
            "zero_seller_rate": summary.get("zero_seller_rate"),
            "total_units_sold": summary.get("total_units_sold", 0),
            "summary": summary,
            "tuning_hints": row.get("tuning_hints", []),
            "status": row.get("status"),
            "error": row.get("error"),
        }
    )


def _backtest_view_model(payload: dict, lookback: int, window: int) -> AttrDict:
    summary = payload.get("summary") or {}
    predictions = payload.get("predictions") or []
    current_weights = summary.get("current_weights") or {}
    return _objectify(
        {
            "status": payload.get("status", "ok"),
            "message": payload.get("message") or "No backtest data available yet.",
            "report_count": payload.get("report_count", 0),
            "score_count": summary.get("score_count", len(predictions)),
            "sales_window_days": window,
            "stats": {
                "total_units_sold": summary.get("total_units_sold", 0),
                "mae": summary.get("mae", 0),
                "rmse": summary.get("rmse", 0),
                "precision_at_high_score": summary.get("precision_at_high_score", 0),
                "recall_of_sellers": summary.get("recall_of_sellers", 0),
                "f1": summary.get("f1", 0),
                "zero_seller_rate": summary.get("zero_seller_rate", 0),
                "zero_seller_count": summary.get("zero_seller_count", 0),
                "avg_predicted_score": summary.get("avg_predicted_score", 0),
                "min_predicted_score": summary.get("min_predicted_score", 0),
                "max_predicted_score": summary.get("max_predicted_score", 0),
            },
            "top_k_analysis": summary.get("top_k_analysis", {}),
            "component_analysis": summary.get("component_analysis", []),
            "action_analysis": summary.get("action_analysis", {}),
            "tuning_hints": summary.get("tuning_hints", []),
            "current_weights": current_weights,
            "predictions": predictions[:500],
            "lookback_reports": lookback,
        }
    )


@bp.route("/settings", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN)
def settings():
    proxy = get_trend_scout_proxy()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_weights":
            weight_type = request.form.get("weight_type", "score")
            prefix_map = {
                "score": ("score", proxy.weight_defaults().get("score", {})),
                "source": ("source", proxy.weight_defaults().get("source", {})),
                "buyer": ("buyer", proxy.weight_defaults().get("buyer", {})),
                "metric": ("metric", proxy.weight_defaults().get("metric", {})),
            }
            group, defaults = prefix_map.get(weight_type, ("score", proxy.weight_defaults().get("score", {})))
            entries = []
            for key in defaults:
                val = request.form.get(f"weight_{key}")
                if val is not None:
                    try:
                        entries.append({"group": group, "key": key, "value": float(val)})
                    except ValueError, TypeError:
                        pass
            if entries:
                proxy.save_weights(entries)
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

                weights = _weights_from_proxy(proxy)
                existing = (
                    db.session.query(Setting)
                    .filter(Setting.key == _profile_storage_key(profile_name))
                    .first()
                )
                if existing:
                    existing.value = json.dumps(weights)
                else:
                    db.session.add(
                        Setting(
                            key=_profile_storage_key(profile_name),
                            value=json.dumps(weights),
                            description=f"Trend Scout profile: {profile_name}",
                            setting_type="json",
                        )
                    )
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
                    for group_key in (
                        "score_weights",
                        "source_weights",
                        "buyer_source_weights",
                        "metric_weights",
                    ):
                        prefix_map = {
                            "score_weights": "score",
                            "source_weights": "source",
                            "buyer_source_weights": "buyer",
                            "metric_weights": "metric",
                        }
                        group = prefix_map.get(group_key)
                        if group and group_key in profile:
                            proxy.save_weights(
                                [
                                    {"group": group, "key": key, "value": float(val)}
                                    for key, val in profile[group_key].items()
                                ]
                            )
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
                proxy.toggle_source(source_key, enabled)
                record_audit_event(
                    action="trend_scout.settings.source_toggled",
                    entity_type="settings",
                    entity_id=f"source_{source_key}",
                    metadata={"source": source_key, "enabled": enabled},
                    source_module=__name__,
                )

        return redirect(url_for("trend_scout.settings"))

    weights = _weights_from_proxy(proxy)
    profiles = _list_profiles()
    defaults = proxy.weight_defaults()
    source_keys = list(defaults.get("source", {}))
    source_enabled_state = {
        item["source"]: bool(item["enabled"])
        for item in proxy.list_source_toggles().get("items", [])
    }

    return render_template(
        "trend_scout/settings.html",
        weights=weights,
        profiles=profiles,
        source_keys=source_keys,
        source_enabled_state=source_enabled_state,
        DEFAULT_SCORE_WEIGHTS=defaults.get("score", {}),
        DEFAULT_SOURCE_WEIGHTS=defaults.get("source", {}),
    )


# -- Phase 9: Report Detail & Comparison --


@bp.get("/reports/<int:report_id>")
@roles_required(UserRole.ADMIN)
def report_detail(report_id: int):
    proxy = get_trend_scout_proxy()
    try:
        report = _objectify(proxy.report_by_id(report_id))
    except TrendScoutUnavailable:
        abort(404)

    compare_id = request.args.get("compare", type=int)
    compare_report = None
    if compare_id:
        try:
            compare_report = _objectify(proxy.report_by_id(compare_id))
        except TrendScoutUnavailable:
            compare_report = None

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    action_filter = request.args.get("action")

    scores_pagination = _pagination_from_response(
        proxy.report_opportunities(report_id, action=action_filter, page=page, per_page=per_page),
        page,
        per_page,
    )

    compare_scores = None
    if compare_report:
        compare_items = proxy.report_opportunities(
            compare_report.id,
            action=action_filter,
            include_dismissed=False,
            page=1,
            per_page=200,
        ).get("items", [])
        compare_scores = {s["keyword"]: s.get("opportunity_score", 0) for s in compare_items}

    source_health = _objectify(proxy.source_health(limit=200).get("items", []))
    all_reports = _objectify(proxy.list_reports(limit=100).get("items", []))

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
    proxy = get_trend_scout_proxy()
    try:
        proxy.report_by_id(report_id)
    except TrendScoutUnavailable:
        abort(404)
    scores = proxy.report_opportunities(report_id, include_dismissed=False, page=1, per_page=200).get("items", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "rank",
            "keyword",
            "title",
            "candidate_type",
            "action",
            "opportunity_score",
            "purchase_intent",
            "trend_velocity",
            "price_resilience",
            "low_saturation",
            "local_fit",
            "production_fit",
            "license_risk",
            "inventory_available",
            "base_price",
            "license_status",
            "match_confidence",
            "sources",
        ]
    )
    for s in scores:
        writer.writerow(
            [
                s.get("rank"),
                s.get("keyword"),
                s.get("title"),
                s.get("candidate_type"),
                s.get("action"),
                s.get("opportunity_score"),
                s.get("purchase_intent"),
                s.get("trend_velocity"),
                s.get("price_resilience"),
                s.get("low_saturation"),
                s.get("local_fit"),
                s.get("production_fit"),
                s.get("license_risk"),
                s.get("inventory_available"),
                str(s.get("base_price")),
                s.get("license_status") or "",
                s.get("match_confidence") or "",
                ", ".join(s.get("sources") or []),
            ]
        )

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

    return f'<span class="text-xs" style="color:var(--color-success);">Queued #{job.id}</span>'


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
    runs = _objectify(get_trend_scout_proxy().task_runs(limit=100).get("items", []))
    return render_template("trend_scout/monitor.html", runs=runs)


@bp.get("/monitor/<run_id>")
@roles_required(UserRole.ADMIN)
def task_monitor_detail(run_id: str):
    try:
        run = _objectify(get_trend_scout_proxy().task_run(run_id))
    except TrendScoutUnavailable:
        abort(404)
    report = None
    if run.get("report_id"):
        try:
            report = _objectify(get_trend_scout_proxy().report_by_id(run.report_id))
        except TrendScoutUnavailable:
            report = None
    return render_template("trend_scout/monitor_detail.html", run=run, report=report)


@bp.post("/monitor/<run_id>/cancel")
@roles_required(UserRole.ADMIN)
def task_monitor_cancel(run_id: str):
    try:
        run = get_trend_scout_proxy().task_run(run_id)
        if run.get("status") not in ("pending", "running"):
            return jsonify({"error": f"Cannot cancel task with status '{run.get('status')}'"}), 400
        get_trend_scout_proxy().pipeline_cancel(run_id)
    except TrendScoutUnavailable as exc:
        return _json_error(exc, 404)
    record_audit_event(
        action="trend_scout.task_cancelled",
        entity_type="trend_task_run",
        entity_id=run_id,
        metadata={"celery_task_id": run.get("celery_task_id"), "trigger": run.get("trigger")},
        source_module=__name__,
    )
    return jsonify({"status": "cancelled"})


@bp.post("/monitor/<run_id>/retry")
@roles_required(UserRole.ADMIN)
def task_monitor_retry(run_id: str):
    proxy = get_trend_scout_proxy()
    try:
        run = proxy.task_run(run_id)
        if run.get("status") != "failed":
            return jsonify({"error": f"Can only retry failed tasks, status is '{run.get('status')}'"}), 400
        payload = proxy.run_pipeline(trigger=f"retry:{run_id}")
    except TrendScoutUnavailable as exc:
        return _json_error(exc, 404)
    session["trend_scout_task_id"] = payload.get("run_id") or payload.get("task_id")
    record_audit_event(
        action="trend_scout.task_retried",
        entity_type="trend_task_run",
        entity_id=run_id,
        metadata={"new_celery_task_id": payload.get("task_id"), "trigger": run.get("trigger")},
        source_module=__name__,
    )
    return jsonify({"task_id": payload.get("task_id"), "run_id": payload.get("run_id"), "status": "dispatched"})


# -- Phase 11: Calibration History & Comparison --


@bp.get("/calibration")
@roles_required(UserRole.ADMIN)
def calibration():
    proxy = get_trend_scout_proxy()
    if request.args.get("run") == "1":
        result = proxy.run_calibration()
        record_audit_event(
            action="trend_scout.calibration.manual_run",
            entity_type="trend_calibration_result",
            entity_id=str(result.get("id") or result.get("run_id") or "manual"),
            metadata={
                "mae": result.get("mae"),
                "precision": result.get("precision_at_high_score"),
                "report_count": result.get("report_count"),
            },
            source_module=__name__,
        )
        return redirect(url_for("trend_scout.calibration"))

    history = [_calibration_view_model(item) for item in proxy.calibration_history().get("items", [])]
    comparison = None
    regression = None
    if len(history) >= 2:
        prev, curr = history[1], history[0]
        comparison = {
            "prev_date": prev.run_date,
            "curr_date": curr.run_date,
            "mae_change": (curr.mae - prev.mae)
            if (curr.mae is not None and prev.mae is not None)
            else None,
            "precision_change": (
                (curr.precision_at_high_score - prev.precision_at_high_score)
                if (
                    curr.precision_at_high_score is not None
                    and prev.precision_at_high_score is not None
                )
                else None
            ),
            "f1_change": (curr.f1_score - prev.f1_score)
            if (curr.f1_score is not None and prev.f1_score is not None)
            else None,
            "prev": prev,
            "curr": curr,
        }

    return render_template(
        "trend_scout/calibration.html",
        history=history,
        comparison=comparison,
        regression=regression,
    )


@bp.get("/calibration/<int:cal_id>")
@roles_required(UserRole.ADMIN)
def calibration_detail(cal_id: int):
    history = [_calibration_view_model(item) for item in get_trend_scout_proxy().calibration_history().get("items", [])]
    cal = next((item for item in history if item.get("id") == cal_id), None)
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
    lookback = request.args.get("lookback", 12, type=int)
    window = request.args.get("window", 60, type=int)
    result = get_trend_scout_proxy().run_backtest(lookback_reports=lookback, sales_window_days=window)
    return render_template("trend_scout/backtest.html", result=_backtest_view_model(result, lookback, window))
