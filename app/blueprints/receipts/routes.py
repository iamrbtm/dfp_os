from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.blueprints.receipts import bp
from app.extensions import db
from app.forms.receipt import (
    ReceiptAllocationForm,
    ReceiptReviewForm,
    ReceiptSearchForm,
    ReceiptUploadForm,
)
from app.models import Receipt, ReceiptLineItem, Market, CustomRequest
from app.models.receipt import ReceiptStatus
from app.services.receipt_allocations import (
    allocate_taxes_and_fees,
    bulk_assign_line_items,
    get_reconciliation_summary,
)
from app.services.receipt_audit import record_audit
from app.services.receipt_duplicates import check_duplicates, resolve_duplicate
from app.services.receipts import (
    approve_receipt,
    get_receipt_dashboard,
    process_receipt,
    reject_receipt,
    upload_receipt,
)
from app.utils.auth import roles_required
from app.models.user import UserRole


@bp.route("/")
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF, UserRole.VIEWER)
def dashboard():
    data = get_receipt_dashboard()
    return render_template("receipts/dashboard.html", data=data)


@bp.route("/inbox")
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def inbox():
    search_form = ReceiptSearchForm(request.args)
    query = Receipt.query.filter(Receipt.deleted_at.is_(None))

    status_filter = search_form.status.data if search_form.status.data else None
    if status_filter:
        query = query.filter(Receipt.status == status_filter)

    search_term = search_form.q.data
    if search_term:
        query = query.filter(
            db.or_(
                Receipt.merchant_name.ilike(f"%{search_term}%"),
                Receipt.store_name.ilike(f"%{search_term}%"),
                Receipt.receipt_number.ilike(f"%{search_term}%"),
            )
        )

    receipts = query.order_by(Receipt.created_at.desc()).all()
    return render_template(
        "receipts/inbox.html",
        receipts=receipts,
        search_form=search_form,
        status_filter=status_filter,
        search_term=search_term or "",
        ReceiptStatus=ReceiptStatus,
    )


@bp.route("/upload", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def upload():
    form = ReceiptUploadForm()
    if form.validate_on_submit():
        files = request.files.getlist("files")
        uploaded = []
        errors = []
        for file_obj in files:
            if file_obj and file_obj.filename:
                try:
                    receipt = upload_receipt(
                        file_obj,
                        user_id=current_user.id,
                        source_type=form.source_type.data or "upload",
                    )
                    if receipt:
                        uploaded.append(receipt)
                        record_audit(receipt.id, "receipt_uploaded", current_user.id)
                except ValueError as e:
                    errors.append(str(e))

        if uploaded:
            flash(f"{len(uploaded)} receipt(s) uploaded successfully.", "success")
            for r in uploaded:
                process_receipt(r.id)
            if len(uploaded) == 1:
                return redirect(url_for("receipts.review", receipt_id=uploaded[0].id))
        if errors:
            for e in errors:
                flash(e, "danger")

        return redirect(url_for("receipts.inbox"))

    return render_template("receipts/upload.html", form=form)


@bp.route("/<int:receipt_id>/review", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def review(receipt_id: int):
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt or receipt.deleted_at:
        abort(404)

    form = ReceiptReviewForm(obj=receipt)

    if form.validate_on_submit():
        if form.submit_approve.data:
            result = approve_receipt(receipt_id, current_user.id)
            if result["success"]:
                record_audit(receipt_id, "receipt_approved", current_user.id)
                flash("Receipt approved and expense records created.", "success")
                return redirect(url_for("receipts.dashboard"))
            else:
                for e in result.get("errors", []):
                    flash(e, "danger")

        elif form.submit_reject.data:
            result = reject_receipt(receipt_id, current_user.id)
            if result["success"]:
                record_audit(receipt_id, "receipt_rejected", current_user.id)
                flash("Receipt rejected.", "info")
                return redirect(url_for("receipts.inbox"))
            else:
                for e in result.get("errors", []):
                    flash(e, "danger")

        else:
            receipt.merchant_name = form.merchant_name.data
            receipt.store_name = form.store_name.data
            receipt.store_number = form.store_number.data
            receipt.address_line_1 = form.address_line_1.data
            receipt.address_line_2 = form.address_line_2.data
            receipt.city = form.city.data
            receipt.state = form.state.data
            receipt.postal_code = form.postal_code.data
            receipt.phone = form.phone.data
            receipt.receipt_number = form.receipt_number.data
            receipt.transaction_number = form.transaction_number.data
            receipt.payment_method = form.payment_method.data
            receipt.currency = form.currency.data or "USD"
            receipt.notes = form.notes.data

            for field in ["subtotal", "tax_total", "fee_total", "discount_total", "tip_total", "deposit_total", "grand_total"]:
                val = getattr(form, field).data
                if val:
                    try:
                        from decimal import Decimal
                        setattr(receipt, field, Decimal(str(val)))
                    except (ValueError, TypeError):
                        pass

            if form.date_time.data:
                receipt.date_time = form.date_time.data

            db.session.commit()
            record_audit(receipt_id, "receipt_edited", current_user.id)
            flash("Receipt saved.", "success")
            return redirect(url_for("receipts.review", receipt_id=receipt_id))

    line_items = ReceiptLineItem.query.filter_by(receipt_id=receipt_id).order_by(ReceiptLineItem.row_order).all()
    reconciliation = get_reconciliation_summary(receipt_id)

    return render_template(
        "receipts/review.html",
        receipt=receipt,
        form=form,
        line_items=line_items,
        reconciliation=reconciliation,
        ReceiptStatus=ReceiptStatus,
        low_confidence_threshold=float(current_app.config.get("RECEIPT_LOW_CONFIDENCE_THRESHOLD", 0.8)),
    )


@bp.route("/<int:receipt_id>/line-items/<int:item_id>/edit", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_line_item(receipt_id: int, item_id: int):
    item = db.session.get(ReceiptLineItem, item_id)
    if not item or item.receipt_id != receipt_id:
        abort(404)

    data = request.get_json() or request.form
    if data.get("description") is not None:
        item.description = data["description"]
    if data.get("sku") is not None:
        item.sku = data["sku"]
    if data.get("quantity") is not None:
        try:
            from decimal import Decimal
            item.quantity = Decimal(str(data["quantity"]))
        except (ValueError, TypeError):
            pass
    if data.get("unit_price") is not None:
        try:
            from decimal import Decimal
            item.unit_price = Decimal(str(data["unit_price"]))
        except (ValueError, TypeError):
            pass
    if data.get("line_total") is not None:
        try:
            from decimal import Decimal
            item.line_total = Decimal(str(data["line_total"]))
        except (ValueError, TypeError):
            pass
    if data.get("needs_review") is not None:
        item.needs_review = bool(data["needs_review"])
    if data.get("is_inventory_candidate") is not None:
        item.is_inventory_candidate = bool(data["is_inventory_candidate"])
    if data.get("is_personal_or_excluded") is not None:
        item.is_personal_or_excluded = bool(data["is_personal_or_excluded"])

    db.session.commit()
    record_audit(receipt_id, "line_item_edited", current_user.id)
    flash("Line item updated.", "success")
    return redirect(url_for("receipts.review", receipt_id=receipt_id))


@bp.route("/<int:receipt_id>/assign", methods=["GET", "POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def assign(receipt_id: int):
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt or receipt.deleted_at:
        abort(404)

    form = ReceiptAllocationForm()
    line_items = ReceiptLineItem.query.filter_by(receipt_id=receipt_id).order_by(ReceiptLineItem.row_order).all()
    form.line_item_ids.choices = [(i.id, i.description or f"Item #{i.id}") for i in line_items]

    markets = Market.query.filter_by().order_by(Market.event_date.desc()).all()
    form.market_id.choices = [(0, "\u2014 None \u2014")] + [(m.id, f"{m.name} ({m.event_date})") for m in markets if m.event_date]

    custom_jobs = CustomRequest.query.order_by(CustomRequest.created_at.desc()).all()
    form.custom_job_id.choices = [(0, "\u2014 None \u2014")] + [(j.id, f"#{j.id} {j.name or ''}") for j in custom_jobs]

    if form.validate_on_submit():
        item_ids = form.line_item_ids.data
        atype = form.allocation_type.data
        market_id = form.market_id.data if form.market_id.data and form.market_id.data != 0 else None
        custom_job_id = form.custom_job_id.data if form.custom_job_id.data and form.custom_job_id.data != 0 else None

        count = bulk_assign_line_items(item_ids, atype, market_id=market_id, custom_job_id=custom_job_id)
        record_audit(receipt_id, "line_items_assigned", current_user.id, json.dumps({"count": count, "type": atype}))
        flash(f"{count} line item(s) assigned.", "success")
        return redirect(url_for("receipts.review", receipt_id=receipt_id))

    return render_template(
        "receipts/assign.html",
        receipt=receipt,
        form=form,
        line_items=line_items,
    )


@bp.route("/<int:receipt_id>/allocate-taxes", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def allocate_taxes(receipt_id: int):
    result = allocate_taxes_and_fees(receipt_id)
    if result["success"]:
        record_audit(receipt_id, "adjustments_allocated", current_user.id)
        flash("Taxes and fees allocated.", "success")
    else:
        for e in result.get("errors", []):
            flash(e, "danger")
    return redirect(url_for("receipts.review", receipt_id=receipt_id))


@bp.route("/<int:receipt_id>/check-duplicates", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def check_receipt_duplicates(receipt_id: int):
    result = check_duplicates(receipt_id)
    if result["is_duplicate"]:
        flash(f"Possible duplicate detected (score: {result['score']}).", "warning")
        receipt = db.session.get(Receipt, receipt_id)
        if receipt:
            receipt.status = ReceiptStatus.POSSIBLE_DUPLICATE
            receipt.duplicate_score = result["score"]
            db.session.commit()
    else:
        flash("No duplicates found.", "success")
    return redirect(url_for("receipts.review", receipt_id=receipt_id))


@bp.route("/<int:receipt_id>/resolve-duplicate", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def resolve_receipt_duplicate(receipt_id: int):
    action = request.form.get("action", "keep")
    duplicate_of_id = request.form.get("duplicate_of_id", type=int)
    result = resolve_duplicate(receipt_id, action, duplicate_of_id)
    if result["success"]:
        record_audit(receipt_id, f"duplicate_{action}", current_user.id)
        flash(f"Duplicate resolved ({action}).", "success")
    else:
        for e in result.get("errors", []):
            flash(e, "danger")
    return redirect(url_for("receipts.review", receipt_id=receipt_id))


@bp.route("/<int:receipt_id>/reprocess", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def reprocess(receipt_id: int):
    result = process_receipt(receipt_id)
    if result["success"]:
        record_audit(receipt_id, "receipt_reprocessed", current_user.id)
        flash("Receipt reprocessed.", "success")
    else:
        for e in result.get("errors", []):
            flash(e, "danger")
    return redirect(url_for("receipts.review", receipt_id=receipt_id))


@bp.route("/<int:receipt_id>/archive", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def archive(receipt_id: int):
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        abort(404)
    receipt.deleted_at = datetime.now(timezone.utc)
    receipt.status = ReceiptStatus.ARCHIVED
    db.session.commit()
    record_audit(receipt_id, "receipt_archived", current_user.id)
    flash("Receipt archived.", "success")
    return redirect(url_for("receipts.inbox"))


@bp.route("/duplicates")
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def duplicates():
    receipts = Receipt.query.filter(
        Receipt.status == ReceiptStatus.POSSIBLE_DUPLICATE,
        Receipt.deleted_at.is_(None),
    ).order_by(Receipt.created_at.desc()).all()
    return render_template("receipts/duplicates.html", receipts=receipts, ReceiptStatus=ReceiptStatus)


@bp.route("/settings")
@login_required
@roles_required(UserRole.ADMIN)
def settings():
    return render_template("receipts/settings.html")


@bp.route("/help")
@login_required
def help_page():
    return render_template("receipts/help.html")


@bp.route("/help/download")
@login_required
def help_download():
    from flask import Response
    from pathlib import Path
    help_path = Path(current_app.root_path).parent / "docs" / "receipt-expense-workflow.md"
    if help_path.exists():
        content = help_path.read_text()
    else:
        content = "# Receipt Workflow Help\n\nHelp document not found."
    return Response(
        content,
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment;filename=receipt-expense-workflow.md"},
    )


@bp.route("/<int:receipt_id>/image")
@login_required
def receipt_image(receipt_id: int):
    from flask import send_file
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt or receipt.deleted_at:
        abort(404)
    file_path = receipt.preview_file_id or receipt.original_file_id
    if not file_path or not os.path.exists(file_path):
        abort(404)
    return send_file(file_path)


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    data = get_receipt_dashboard()
    return jsonify({
        "total_this_month": data["total_this_month"],
        "needs_review": data["needs_review"],
        "possible_duplicates": data["possible_duplicates"],
        "approved_total": str(data["approved_total"]),
        "unallocated": data["unallocated"],
    })


@bp.route("/api/process", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def api_process():
    data = request.get_json() or {}
    receipt_id = data.get("receipt_id")
    if not receipt_id:
        return jsonify({"error": "receipt_id is required"}), 400
    result = process_receipt(receipt_id)
    return jsonify(result)


@bp.route("/api/<int:receipt_id>/reconciliation")
@login_required
def api_reconciliation(receipt_id: int):
    summary = get_reconciliation_summary(receipt_id)
    return jsonify({
        k: str(v) if hasattr(v, "quantize") else v
        for k, v in summary.items()
    })


@bp.teardown_request
def teardown(exception=None):
    if exception:
        db.session.rollback()
