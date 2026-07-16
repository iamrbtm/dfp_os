from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    FilamentSpool,
    FilamentStatus,
    PrintFailureAutopsy,
    PrintFailureCategory,
    PrintFailureSeverity,
    PrintJob,
    PrintJobStatus,
    Printer,
    PrinterStatus,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.api_tokens import create_api_token
from app.services.printer_reliability import (
    create_autopsy_for_failed_job,
    get_all_printer_reliability_summaries,
    get_failure_rate_for_cost_engine,
    needs_failure_autopsy,
    resolve_autopsy,
)


def _printer_product_and_jobs():
    category = Category(name="Reliability Category", slug="reliability-category")
    product = Product(
        name="Reliability Dragon",
        slug="reliability-dragon",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
    )
    printer = Printer(name="Reliability A1", model="Bambu A1", status=PrinterStatus.ACTIVE)
    spool = FilamentSpool(
        brand="Bambu",
        material_type="PLA",
        color_name="Blue",
        status=FilamentStatus.ACTIVE,
        cost_per_gram=Decimal("0.0200"),
        remaining_weight_grams=700,
    )
    completed = PrintJob(
        label="Completed reliability print",
        product=product,
        printer=printer,
        status=PrintJobStatus.COMPLETED,
    )
    failed = PrintJob(
        label="Failed reliability print",
        product=product,
        printer=printer,
        status=PrintJobStatus.FAILED,
    )
    db.session.add_all([category, product, printer, spool, completed, failed])
    db.session.commit()
    return printer, product, spool, completed, failed


def test_failure_autopsy_model_relationships_and_audit(app, monkeypatch):
    audit_calls = []
    monkeypatch.setattr(
        "app.services.printer_reliability.record_audit_event",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    with app.app_context():
        printer, product, spool, _completed, failed = _printer_product_and_jobs()
        actor = User(
            email="autopsy-actor@example.com",
            first_name="Autopsy",
            last_name="Actor",
            role=UserRole.ADMIN,
            is_active=True,
        )
        actor.set_password("secret")
        db.session.add(actor)
        db.session.commit()
        autopsy = PrintFailureAutopsy(
            category=PrintFailureCategory.ADHESION,
            severity=PrintFailureSeverity.HIGH,
            filament_spool=spool,
            notes="Corner lifted after first layer.",
            corrective_action="Clean plate and raise bed temp.",
            maintenance_required=True,
        )

        create_autopsy_for_failed_job(failed, autopsy, actor_id=actor.id)

        assert autopsy.id is not None
        assert autopsy.print_job_id == failed.id
        assert autopsy.printer_id == printer.id
        assert autopsy.product_id == product.id
        assert failed.failure_autopsies[0].category == PrintFailureCategory.ADHESION
        assert needs_failure_autopsy(failed) is False
        assert audit_calls[-1]["action"] == "print_failure_autopsy.created"

        resolve_autopsy(autopsy, resolution_notes="Plate cleaned.", actor_id=actor.id)
        assert autopsy.resolved is True
        assert audit_calls[-1]["action"] == "print_failure_autopsy.resolved"


def test_reliability_summary_and_cost_engine_failure_rate(app):
    with app.app_context():
        printer, _product, spool, _completed, failed = _printer_product_and_jobs()
        autopsy = PrintFailureAutopsy(
            print_job=failed,
            printer=printer,
            category=PrintFailureCategory.CLOG,
            severity=PrintFailureSeverity.MEDIUM,
            filament_spool=spool,
        )
        db.session.add(autopsy)
        db.session.commit()

        summaries = get_all_printer_reliability_summaries()

        assert len(summaries) == 1
        summary = summaries[0]
        assert summary.completed_count == 1
        assert summary.failed_count == 1
        assert summary.failure_rate == Decimal("0.5000")
        assert summary.common_causes[0]["category"] == "clog"
        assert get_failure_rate_for_cost_engine(printer_model="Bambu A1") == Decimal("0.5000")


def test_print_job_failure_autopsy_browser_workflow(client, admin_user, app):
    with app.app_context():
        _printer, _product, spool, _completed, failed = _printer_product_and_jobs()
        failed_id = failed.id
        spool_id = spool.id
    with app.app_context():
        assert isinstance(failed_id, int)
        assert db.session.get(PrintJob, failed_id) is not None

    client.post(
        "/auth/login",
        data={"email": admin_user["email"], "password": admin_user["password"]},
    )
    detail = client.get(f"/print-jobs/{failed_id}")
    assert detail.status_code == 200, detail.data[:500]
    assert b"needs a failure autopsy" in detail.data

    response = client.post(
        f"/print-jobs/{failed_id}/autopsy",
        data={
            "category": PrintFailureCategory.SPAGHETTI.value,
            "severity": PrintFailureSeverity.HIGH.value,
            "filament_spool_id": str(spool_id),
            "notes": "Detached overnight.",
            "corrective_action": "Add brim.",
            "maintenance_required": "y",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Spaghetti" in response.data
    assert b"Add brim" in response.data


def test_printer_reliability_api_and_report_studio(client, admin_user, app):
    with app.app_context():
        _printer_product_and_jobs()
        user = User(
            email="inventory-token@example.com",
            first_name="Inventory",
            last_name="Token",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _token, raw = create_api_token(user, "Inventory API", scopes=["admin"])

    api_response = client.get(
        "/api/v1/printers/reliability",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert api_response.status_code == 200, api_response.get_json()
    payload = api_response.get_json()
    assert payload["data"][0]["printer_name"] == "Reliability A1"
    assert payload["data"][0]["failure_rate_percent"] == 50.0

    client.post(
        "/auth/login",
        data={"email": admin_user["email"], "password": admin_user["password"]},
    )
    report_response = client.get("/report-studio/printer-reliability")
    assert report_response.status_code == 200
    assert b"Printer Reliability" in report_response.data
    assert b"Reliability A1" in report_response.data
