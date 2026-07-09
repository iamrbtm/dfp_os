from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.intelligence import bp
from app.models import UserRole
from app.services.audit import record_audit_event
from app.services.intelligence_client import get_intelligence_client
from app.utils.auth import roles_required


def _has_error(payload: dict) -> bool:
    return isinstance(payload, dict) and bool(payload.get("error"))


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def index():
    client = get_intelligence_client()
    health = client.health_ready()
    products = client.product_summaries(limit=10)
    outcomes = client.decision_outcomes(limit=10)
    return render_template(
        "intelligence/index.html",
        configured=client.is_configured(),
        health=health,
        products=products.get("items", []) if not _has_error(products) else [],
        outcomes=outcomes.get("items", []) if not _has_error(outcomes) else [],
        error=health.get("error") if _has_error(health) else None,
    )


@bp.post("/warehouse/rebuild-square")
@roles_required(UserRole.ADMIN)
def rebuild_square():
    result = get_intelligence_client().rebuild_square_warehouse()
    if _has_error(result):
        flash("Square warehouse rebuild failed. Check service configuration and logs.", "danger")
    else:
        flash(f"Warehouse rebuild complete: {result.get('fact_rows', 0)} fact rows.", "success")
        record_audit_event(
            action="intelligence.warehouse_rebuilt",
            entity_type="intelligence_warehouse",
            entity_id=result.get("id"),
            after_state=result,
            source_module=__name__,
        )
    return redirect(url_for("intelligence.index"))


@bp.route("/ask", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def ask():
    result = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            result = get_intelligence_client().ask(question)
            if _has_error(result):
                flash("Ask DFP could not get an evidence-backed answer.", "danger")
            else:
                record_audit_event(
                    action="intelligence.ask_dfp",
                    entity_type="ask_dfp_run",
                    entity_id=result.get("id"),
                    after_state={"question": question},
                    source_module=__name__,
                )
        else:
            flash("Enter a question first.", "warning")
    return render_template("intelligence/ask.html", result=result, question=question)


@bp.get("/legacy")
@roles_required(UserRole.ADMIN)
def legacy_management():
    client = get_intelligence_client()
    tables = client.legacy_list_tables()
    promoted = client.legacy_list_promoted()
    return render_template(
        "intelligence/legacy.html",
        tables=tables.get("tables", tables.get("items", [])) if not _has_error(tables) else [],
        promoted=promoted if isinstance(promoted, list) and not _has_error(promoted) else [],
        error=promoted.get("error") if _has_error(promoted) else tables.get("error") if _has_error(tables) else None,
    )


@bp.post("/legacy/promote")
@roles_required(UserRole.ADMIN)
def legacy_promote():
    result = get_intelligence_client().legacy_promote()
    if _has_error(result):
        flash("Promotion failed. Check that tables are reviewed and marked as keep.", "danger")
    else:
        flash(f"Promoted {result.get('promoted', 0)} tables.", "success")
        record_audit_event(
            action="intelligence.legacy_promoted",
            entity_type="legacy_import",
            entity_id=result.get("id"),
            after_state={"promoted_count": result.get("promoted")},
            source_module=__name__,
        )
    return redirect(url_for("intelligence.legacy_management"))


@bp.post("/legacy/cleanup-staging")
@roles_required(UserRole.ADMIN)
def legacy_cleanup_staging():
    result = get_intelligence_client().legacy_cleanup_staging()
    if _has_error(result):
        flash("Staging cleanup failed.", "danger")
    else:
        flash("Staging data cleared.", "success")
        record_audit_event(
            action="intelligence.legacy_staging_cleaned",
            entity_type="legacy_import",
            entity_id="all",
            after_state=result,
            source_module=__name__,
        )
    return redirect(url_for("intelligence.legacy_management"))


@bp.post("/legacy/rebuild-warehouse")
@roles_required(UserRole.ADMIN)
def legacy_rebuild_warehouse():
    result = get_intelligence_client().rebuild_legacy_warehouse()
    if _has_error(result):
        flash("Legacy warehouse rebuild failed.", "danger")
    else:
        flash(f"Legacy warehouse rebuilt: {result.get('facts_created', 0)} fact rows.", "success")
        record_audit_event(
            action="intelligence.legacy_warehouse_rebuilt",
            entity_type="intelligence_warehouse",
            entity_id=result.get("id"),
            after_state=result,
            source_module=__name__,
        )
    return redirect(url_for("intelligence.legacy_management"))


@bp.get("/pipeline")
@roles_required(UserRole.ADMIN)
def pipeline_status():
    client = get_intelligence_client()
    status = client.pipeline_status()
    return render_template(
        "intelligence/pipeline.html",
        status=status if not _has_error(status) else None,
        error=status.get("error") if _has_error(status) else None,
    )


@bp.post("/pipeline/run")
@roles_required(UserRole.ADMIN)
def pipeline_run():
    result = get_intelligence_client().run_normalized_pipeline()
    if _has_error(result):
        flash("Normalized pipeline run failed.", "danger")
    else:
        flash(f"Pipeline complete: {result.get('entities_created', 0)} entities.", "success")
        record_audit_event(
            action="intelligence.pipeline_run",
            entity_type="normalized_pipeline",
            entity_id=result.get("id"),
            after_state=result,
            source_module=__name__,
        )
    return redirect(url_for("intelligence.pipeline_status"))


@bp.route("/market-advisor", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def market_advisor():
    result = None
    if request.method == "POST":
        inventory: dict[str, int] = {}
        for line in request.form.get("inventory_by_product_key", "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            try:
                inventory[key.strip()] = max(int(value.strip()), 0)
            except ValueError:
                continue
        payload = {
            "market_name": request.form.get("market_name", "").strip(),
            "market_date": request.form.get("market_date") or None,
            "event_type": request.form.get("event_type") or None,
            "expected_foot_traffic": int(request.form.get("expected_foot_traffic") or 0) or None,
            "booth_fee_cents": int(float(request.form.get("booth_fee", "0") or 0) * 100) or None,
            "inventory_by_product_key": inventory,
            "max_products": int(request.form.get("max_products") or 12),
        }
        if payload["market_name"]:
            result = get_intelligence_client().market_advisor(payload)
            if _has_error(result):
                flash("Market Advisor could not generate recommendations.", "danger")
            else:
                record_audit_event(
                    action="intelligence.market_advisor.generated",
                    entity_type="market_advisor_run",
                    entity_id=result.get("id"),
                    after_state={"market_name": payload["market_name"]},
                    source_module=__name__,
                )
        else:
            flash("Market name is required.", "warning")
    return render_template("intelligence/market_advisor.html", result=result)


@bp.route("/notes", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def notes():
    search_result = None
    query = request.args.get("q", "")
    if request.method == "POST":
        payload = {
            "source": request.form.get("source", "manual"),
            "title": request.form.get("title", "").strip(),
            "document_type": request.form.get("document_type", "market_note"),
            "source_ref": request.form.get("source_ref") or None,
            "content": request.form.get("content", "").strip(),
            "metadata": {},
        }
        if payload["title"] and payload["content"]:
            result = get_intelligence_client().create_document(payload)
            if _has_error(result):
                flash("Could not save intelligence note.", "danger")
            else:
                flash("Intelligence note saved.", "success")
        else:
            flash("Title and content are required.", "warning")
        return redirect(url_for("intelligence.notes"))
    if query:
        search_result = get_intelligence_client().search_knowledge(query)
    return render_template("intelligence/notes.html", query=query, search_result=search_result)


@bp.post("/decision-outcomes")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def decision_outcomes():
    payload = {
        "recommendation_id": request.form.get("recommendation_id") or None,
        "run_id": request.form.get("run_id") or None,
        "decision_type": request.form.get("decision_type") or "market_advisor",
        "user_action": request.form.get("user_action") or "accepted",
        "outcome_status": request.form.get("outcome_status") or "unknown",
        "actual_units": int(request.form.get("actual_units") or 0) if request.form.get("actual_units") else None,
        "actual_revenue_cents": int(float(request.form.get("actual_revenue") or 0) * 100)
        if request.form.get("actual_revenue")
        else None,
        "notes": request.form.get("notes") or None,
        "created_by": str(getattr(current_user, "id", "") or ""),
    }
    result = get_intelligence_client().record_outcome(payload)
    if _has_error(result):
        flash("Could not record decision outcome.", "danger")
    else:
        flash("Decision outcome recorded.", "success")
    return redirect(url_for("intelligence.index"))
