from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.imports import LegacyTableReviewRequest
from app.security import verify_internal_token
from app.services.legacy_mariadb import list_imported_tables, review_table
from app.services.legacy_promotion import promote_kept_tables
from app.config import settings

router = APIRouter(
    prefix="/admin",
    tags=["legacy-review-gui"],
    dependencies=[Depends(verify_internal_token)],
)

jinja_env = Environment(loader=FileSystemLoader("app/templates"), cache_size=0)
templates = Jinja2Templates(env=jinja_env)

EXCLUDE_PATTERNS = [
    "session", "cache", "log", "temp", "backup", "Migration",
    "sys_", "debug", "error", "audit_log", "import_batch",
    "LegacyMariaDbTableSnapshot", "legacy_import", "legacy_table",
]

PRODUCT_PATTERNS = [
    "product", "category", "collection", "variant", "sku",
]

BUSINESS_PATTERNS = [
    "customer", "order", "invoice", "payment", "inventory",
    "printer", "print_job", "filament", "spool", "market",
    "receipt", "expense", "prep_task", "shipment",
]


def _recommend(table_name: str) -> tuple[str, str]:
    lower = table_name.lower()

    if any(p in lower for p in EXCLUDE_PATTERNS):
        return ("exclude", f"Likely system/internal table based on name pattern ({lower}).")

    if any(p in lower for p in PRODUCT_PATTERNS):
        return ("keep", f"Contains product-related data — likely useful for normalization.")

    if any(p in lower for p in BUSINESS_PATTERNS):
        return ("keep", f"Contains business records — likely useful for normalization.")

    return ("keep", "No obvious system pattern detected. Keep by default for human review.")


@router.get("/legacy-import-review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    saved: bool = False,
    errors: list[str] | None = None,
    promoted: str | None = None,
):
    result = await list_imported_tables(db)
    tables = []
    for t in result.tables:
        rec_action, rec_note = _recommend(t.table_name)
        tables.append({
            "table_name": t.table_name,
            "staged_row_count": t.staged_row_count,
            "columns": t.columns,
            "primary_key_columns": t.primary_key_columns,
            "recommended_action": rec_action,
            "recommendation_note": rec_note,
            "review_decision": t.review_decision,
            "review_notes": t.review_notes,
        })

    import json
    promoted_data: dict | None = None
    if promoted:
        try:
            promoted_data = json.loads(promoted)
        except (json.JSONDecodeError, TypeError):
            pass

    return templates.TemplateResponse(
        request,
        "legacy_review.html",
        {
            "service_name": settings.service_name,
            "api_token": settings.internal_api_token,
            "tables": tables,
            "saved": saved,
            "errors": errors or [],
            "promoted": promoted_data,
        },
    )


@router.post("/legacy-import-review", response_class=HTMLResponse)
async def review_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    table_names = set()
    decisions: dict[str, str] = {}
    notes: dict[str, str] = {}

    for key in form:
        if key.startswith("decision_"):
            table_name = key[len("decision_"):]
            table_names.add(table_name)
            decisions[table_name] = str(form[key])
        elif key.startswith("note_"):
            table_name = key[len("note_"):]
            notes[table_name] = str(form[key])

    saved_errors: list[str] = []
    any_saved = False
    for table_name in table_names:
        decision = decisions.get(table_name, "keep")
        note = notes.get(table_name, "")
        try:
            payload = LegacyTableReviewRequest(
                decision=decision,
                notes=note or None,
                confirm_delete=(decision == "delete_staging"),
            )
            await review_table(db, table_name, payload)
            any_saved = True
        except ValueError as exc:
            saved_errors.append(f"{table_name}: {exc}")

    if saved_errors:
        return await review_page(request, db, saved=any_saved, errors=saved_errors)

    return RedirectResponse(
        url=f"/admin/legacy-import-review?saved=1&token={settings.internal_api_token}",
        status_code=303,
    )


@router.post("/legacy-import-review/promote", response_class=HTMLResponse)
async def promote_handler(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    import json
    result = await promote_kept_tables(db)
    promoted_json = json.dumps(result)
    return RedirectResponse(
        url=f"/admin/legacy-import-review?promoted={promoted_json}&token={settings.internal_api_token}",
        status_code=303,
    )
