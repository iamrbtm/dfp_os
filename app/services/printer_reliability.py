from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


from app.extensions import db
from app.models import (
    PrintFailureAutopsy,
    PrintFailureCategory,
    PrintJob,
    PrintJobStatus,
    Printer,
    User,
)
from app.services.admin_mutations import snapshot_instance
from app.services.audit import record_audit_event


@dataclass(frozen=True)
class PrinterReliabilitySummary:
    printer_id: int
    printer_name: str
    printer_model: str
    completed_count: int
    failed_count: int
    active_count: int
    total_finished_count: int
    failure_rate: Decimal
    common_causes: list[dict[str, object]]
    affected_products: list[dict[str, object]]
    filament_correlations: list[dict[str, object]]
    recent_trend: str


def create_autopsy_for_failed_job(
    print_job: PrintJob,
    autopsy: PrintFailureAutopsy,
    *,
    actor_id: int | None = None,
) -> PrintFailureAutopsy:
    db.session.add(autopsy)
    _sync_autopsy_links(print_job, autopsy, actor_id=actor_id)
    print_job.status = PrintJobStatus.FAILED
    if autopsy.notes and not print_job.failure_reason:
        print_job.failure_reason = autopsy.notes
    db.session.add(print_job)
    db.session.commit()
    _record_autopsy_audit("print_failure_autopsy.created", autopsy, actor_id=actor_id)
    return autopsy


def update_autopsy(
    autopsy: PrintFailureAutopsy,
    *,
    before_state: dict,
    actor_id: int | None = None,
) -> PrintFailureAutopsy:
    db.session.add(autopsy)
    db.session.commit()
    _record_autopsy_audit(
        "print_failure_autopsy.updated",
        autopsy,
        before_state=before_state,
        actor_id=actor_id,
    )
    return autopsy


def resolve_autopsy(
    autopsy: PrintFailureAutopsy,
    *,
    resolution_notes: str | None = None,
    actor_id: int | None = None,
) -> PrintFailureAutopsy:
    before_state = snapshot_instance(autopsy)
    autopsy.resolved = True
    if resolution_notes:
        autopsy.resolution_notes = resolution_notes
    db.session.add(autopsy)
    db.session.commit()
    _record_autopsy_audit(
        "print_failure_autopsy.resolved",
        autopsy,
        before_state=before_state,
        actor_id=actor_id,
    )
    return autopsy


def needs_failure_autopsy(print_job: PrintJob) -> bool:
    return print_job.status == PrintJobStatus.FAILED and not print_job.failure_autopsies


def get_printer_reliability_summary(printer: Printer) -> PrinterReliabilitySummary:
    jobs = PrintJob.query.filter(PrintJob.printer_id == printer.id).all()
    completed = sum(1 for job in jobs if job.status == PrintJobStatus.COMPLETED)
    failed = sum(1 for job in jobs if job.status == PrintJobStatus.FAILED)
    active = sum(1 for job in jobs if job.status in {PrintJobStatus.QUEUED, PrintJobStatus.PRINTING, PrintJobStatus.PAUSED})
    total_finished = completed + failed
    failure_rate = _rate(failed, total_finished)
    autopsies = PrintFailureAutopsy.query.filter(PrintFailureAutopsy.printer_id == printer.id).all()
    return PrinterReliabilitySummary(
        printer_id=printer.id,
        printer_name=printer.name,
        printer_model=printer.model,
        completed_count=completed,
        failed_count=failed,
        active_count=active,
        total_finished_count=total_finished,
        failure_rate=failure_rate,
        common_causes=_common_causes(autopsies),
        affected_products=_affected_products(autopsies),
        filament_correlations=_filament_correlations(autopsies),
        recent_trend=_recent_trend(jobs),
    )


def get_all_printer_reliability_summaries() -> list[PrinterReliabilitySummary]:
    printers = Printer.query.order_by(Printer.name).all()
    return [get_printer_reliability_summary(printer) for printer in printers]


def get_failure_rate_for_cost_engine(*, printer_model: str | None = None) -> Decimal | None:
    query = PrintJob.query
    if printer_model:
        query = query.join(Printer, PrintJob.printer_id == Printer.id).filter(Printer.model == printer_model)
    completed = query.filter(PrintJob.status == PrintJobStatus.COMPLETED).count()
    failed = query.filter(PrintJob.status == PrintJobStatus.FAILED).count()
    total = completed + failed
    if total == 0:
        return None
    return _rate(failed, total)


def get_reliability_report_rows() -> list[dict[str, object]]:
    return [
        {
            "printer_id": summary.printer_id,
            "printer_name": summary.printer_name,
            "printer_model": summary.printer_model,
            "completed_count": summary.completed_count,
            "failed_count": summary.failed_count,
            "active_count": summary.active_count,
            "failure_rate": float(summary.failure_rate),
            "failure_rate_percent": float(summary.failure_rate * Decimal("100")),
            "common_causes": summary.common_causes,
            "affected_products": summary.affected_products,
            "filament_correlations": summary.filament_correlations,
            "recent_trend": summary.recent_trend,
        }
        for summary in get_all_printer_reliability_summaries()
    ]


def _sync_autopsy_links(
    print_job: PrintJob,
    autopsy: PrintFailureAutopsy,
    *,
    actor_id: int | None,
) -> None:
    autopsy.print_job = print_job
    autopsy.printer_id = print_job.printer_id
    autopsy.product_id = print_job.product_id
    if actor_id is not None and db.session.get(User, actor_id) is not None:
        autopsy.user_id = actor_id


def _record_autopsy_audit(
    action: str,
    autopsy: PrintFailureAutopsy,
    *,
    before_state: dict | None = None,
    actor_id: int | None = None,
) -> None:
    record_audit_event(
        action=action,
        entity_type="print_failure_autopsy",
        entity_id=autopsy.id,
        before_state=before_state,
        after_state=snapshot_instance(autopsy),
        source_module=__name__,
        actor_id=actor_id,
    )


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.0000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def _common_causes(autopsies: Iterable[PrintFailureAutopsy]) -> list[dict[str, object]]:
    counts = Counter(autopsy.category for autopsy in autopsies)
    return [
        {"category": category.value, "label": category.value.replace("_", " ").title(), "count": count}
        for category, count in counts.most_common(5)
        if category != PrintFailureCategory.UNKNOWN or count
    ]


def _affected_products(autopsies: Iterable[PrintFailureAutopsy]) -> list[dict[str, object]]:
    counts: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    for autopsy in autopsies:
        if autopsy.product_id and autopsy.product:
            counts[autopsy.product_id] += 1
            names[autopsy.product_id] = autopsy.product.name
    return [
        {"product_id": product_id, "product_name": names[product_id], "count": count}
        for product_id, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]


def _filament_correlations(autopsies: Iterable[PrintFailureAutopsy]) -> list[dict[str, object]]:
    counts: dict[int, int] = defaultdict(int)
    labels: dict[int, str] = {}
    for autopsy in autopsies:
        if autopsy.filament_spool_id and autopsy.filament_spool:
            spool = autopsy.filament_spool
            counts[spool.id] += 1
            labels[spool.id] = f"{spool.brand} {spool.material_type} {spool.color_name}"
    return [
        {"filament_spool_id": spool_id, "label": labels[spool_id], "count": count}
        for spool_id, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    ]


def _recent_trend(jobs: list[PrintJob]) -> str:
    finished_jobs = [
        job for job in jobs if job.status in {PrintJobStatus.COMPLETED, PrintJobStatus.FAILED}
    ]
    finished_jobs.sort(key=lambda job: job.completed_at or job.updated_at or job.created_at)
    if len(finished_jobs) < 4:
        return "insufficient_data"
    midpoint = len(finished_jobs) // 2
    early_rate = _rate(
        sum(1 for job in finished_jobs[:midpoint] if job.status == PrintJobStatus.FAILED),
        len(finished_jobs[:midpoint]),
    )
    recent_rate = _rate(
        sum(1 for job in finished_jobs[midpoint:] if job.status == PrintJobStatus.FAILED),
        len(finished_jobs[midpoint:]),
    )
    if recent_rate > early_rate:
        return "worsening"
    if recent_rate < early_rate:
        return "improving"
    return "steady"
