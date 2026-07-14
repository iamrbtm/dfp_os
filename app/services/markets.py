from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from flask import current_app
from sqlalchemy import func
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Expense,
    Market,
    MarketDocument,
    MarketDocumentType,
    MarketHotelBooking,
    MarketPackingList,
    MarketStatus,
    MarketTimelineEvent,
    MarketWeatherSnapshot,
    Order,
    PosSale,
    PosSession,
    PosSessionStatus,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
)
from app.models.base import utc_now
from app.services.audit_client import get_audit_client
from app.services.cost_engine import estimate_market_profit
from app.services.intelligence_client import get_intelligence_client
from app.services.storage import (
    content_type_for_name,
    upload_file_to_storage,
)


ALLOWED_MARKET_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def get_market_performance(market: Market) -> dict:
    total_sales = _get_market_sales_total(market)
    total_expenses = _get_market_expenses_total(market)
    booth_cost = (market.booth_fee or Decimal(0)) + (market.application_fee or Decimal(0))
    units_sold = _get_units_sold(market)
    cost_engine = estimate_market_profit(market.id)
    packing_list = MarketPackingList.query.filter_by(market_id=market.id).all()
    shrinkage_pct = _calc_reconciliation(packing_list)["shrinkage_pct"]

    return {
        "market": market,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "booth_cost": booth_cost,
        "estimated_profit": total_sales - total_expenses - booth_cost,
        "cost_engine": cost_engine,
        "repeat_recommendation": _repeat_recommendation(
            revenue=cost_engine["revenue"],
            profit=cost_engine["profit"],
            margin_percent=cost_engine["margin_percent"],
            units_sold=units_sold,
            shrinkage_pct=shrinkage_pct,
        ),
        "booth_fee_pct": _calc_pct(booth_cost, total_sales),
        "top_products": _get_top_products(market),
        "payment_methods": _get_payment_methods(market),
        "units_sold": units_sold,
    }


def _calc_reconciliation(packing_list: list[MarketPackingList]) -> dict:
    items = []
    total_took = 0
    total_sold = 0
    total_returned = 0
    total_shrinkage = 0
    for pl in packing_list:
        planned = pl.planned_quantity or 0
        packed = pl.packed_quantity or 0
        sold = pl.sold_quantity or 0
        returned = pl.returned_quantity or 0
        took = packed if packed > 0 else planned
        expected_back = max(took - sold, 0)
        shrinkage = max(expected_back - returned, 0)
        total_took += took
        total_sold += sold
        total_returned += returned
        total_shrinkage += shrinkage
        items.append({
            "product_name": pl.product.name if pl.product else f"Product #{pl.product_id}",
            "packing_id": pl.id,
            "planned": planned,
            "packed": packed,
            "sold": sold,
            "returned": returned,
            "took": took,
            "expected_back": expected_back,
            "shrinkage": shrinkage,
        })
    shrinkage_pct = round((total_shrinkage / total_took) * 100, 1) if total_took > 0 else None
    return {
        "item_list": items,
        "total_took": total_took,
        "total_sold": total_sold,
        "total_returned": total_returned,
        "total_shrinkage": total_shrinkage,
        "shrinkage_pct": shrinkage_pct,
    }


def _merge_reconciliation_items(items: list[dict]) -> list[dict]:
    seen = {}
    for item in items:
        key = item["product_name"]
        if key in seen:
            m = seen[key]
            m["planned"] += item["planned"]
            m["packed"] += item["packed"]
            m["sold"] += item["sold"]
            m["returned"] += item["returned"]
        else:
            seen[key] = dict(item, packing_id=item["packing_id"])
    for item in seen.values():
        took = item["packed"] if item["packed"] > 0 else item["planned"]
        expected_back = max(took - item["sold"], 0)
        shrinkage = max(expected_back - item["returned"], 0)
        item["took"] = took
        item["expected_back"] = expected_back
        item["shrinkage"] = shrinkage
    return list(seen.values())


def get_market_command_center(market: Market) -> dict:
    performance = get_market_performance(market)
    packing_list = MarketPackingList.query.filter_by(market_id=market.id).order_by(
        MarketPackingList.product_id
    ).all()
    tasks = PrepTask.query.filter_by(market_id=market.id).order_by(
        PrepTask.status.asc(), PrepTask.due_at.is_(None).asc(), PrepTask.due_at.asc(), PrepTask.created_at.desc()
    ).all()
    timeline_events = MarketTimelineEvent.query.filter_by(market_id=market.id).order_by(
        MarketTimelineEvent.starts_at.is_(None).asc(), MarketTimelineEvent.starts_at.asc(), MarketTimelineEvent.created_at.desc()
    ).all()
    weather = MarketWeatherSnapshot.query.filter_by(market_id=market.id).order_by(
        MarketWeatherSnapshot.fetched_at.desc()
    ).first()
    hotels = MarketHotelBooking.query.filter_by(market_id=market.id).order_by(
        MarketHotelBooking.check_in_date.is_(None).asc(), MarketHotelBooking.check_in_date.asc(), MarketHotelBooking.created_at.desc()
    ).all()
    documents = MarketDocument.query.filter_by(market_id=market.id).order_by(
        MarketDocument.created_at.desc()
    ).all()
    marketing_tasks = [task for task in tasks if task.category == PrepTaskCategory.MARKETING]
    todo_tasks = [task for task in tasks if task.category != PrepTaskCategory.MARKETING]
    from app.services.prep_tasks import market_readiness_score
    readiness = market_readiness_score(market.id)
    reconciliation = _calc_reconciliation(packing_list)
    reconciliation["item_list"] = _merge_reconciliation_items(reconciliation["item_list"])
    return {
        "performance": performance,
        "packing_list": packing_list,
        "tasks": tasks,
        "marketing_tasks": marketing_tasks,
        "todo_tasks": todo_tasks,
        "timeline_events": timeline_events,
        "latest_weather": weather,
        "hotel_bookings": hotels,
        "documents": documents,
        "recommendations": get_market_advisor_recommendations(market),
        "readiness": readiness,
        "stats": _quick_stats(market, packing_list, tasks, timeline_events, documents, performance),
        "recent_activity": _recent_activity(market, tasks, timeline_events, hotels, documents, packing_list),
        "reconciliation": reconciliation,
    }


def get_market_advisor_recommendations(market: Market) -> list[dict]:
    client = get_intelligence_client()
    if not client.is_configured():
        return []
    booth_fee_cents = None
    if market.booth_fee is not None:
        booth_fee_cents = int(Decimal(str(market.booth_fee)) * 100)
    if market.application_fee is not None:
        booth_fee_cents = (booth_fee_cents or 0) + int(Decimal(str(market.application_fee)) * 100)
    payload = {
        "market_name": market.name,
        "market_date": market.event_date.isoformat() if market.event_date else None,
        "event_type": "vendor_market",
        "expected_foot_traffic": _parse_traffic(market.expected_traffic),
        "booth_fee_cents": booth_fee_cents,
        "inventory_by_product_key": {},
        "max_products": 12,
    }
    result = client.market_advisor(payload)
    if isinstance(result, dict) and result.get("error"):
        return []
    return result.get("recommendations", []) if isinstance(result, dict) else []


def _parse_traffic(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parts = value.replace(",", "").split("-")
        if len(parts) == 2:
            return (int(parts[0].strip()) + int(parts[1].strip())) // 2
        return int(parts[0].strip())
    except (ValueError, IndexError):
        return None


def geocode_market_address(market: Market, actor=None) -> bool:
    """Populate latitude/longitude from the market address via the US Census geocoder."""
    query = _market_address_query(market)
    if not query:
        return False

    params = urlencode(
        {
            "address": query,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
    )
    url = f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?{params}"
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(url)
            response.raise_for_status()
            matches = response.json().get("result", {}).get("addressMatches", [])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        current_app.logger.info("market geocoding failed for market %s: %s", market.id, exc)
        return False

    if not matches:
        return False
    coordinates = matches[0].get("coordinates") or {}
    latitude = coordinates.get("y")
    longitude = coordinates.get("x")
    if latitude is None or longitude is None:
        return False

    before = {"latitude": market.latitude, "longitude": market.longitude}
    market.latitude = float(latitude)
    market.longitude = float(longitude)
    record_market_audit(
        "market.geocoded",
        "market",
        market.id,
        actor=actor,
        before_state=before,
        after_state={"latitude": market.latitude, "longitude": market.longitude},
        metadata={"address": query},
    )
    return True


def complete_prep_task(task: PrepTask, actor=None) -> PrepTask:
    task.status = PrepTaskStatus.COMPLETED
    task.completed_at = utc_now()
    db.session.commit()
    record_market_audit(
        "prep_task.completed",
        "prep_task",
        task.id,
        actor=actor,
        after_state={"title": task.title, "market_id": task.market_id, "status": task.status.value},
    )
    return task


def complete_timeline_event(event: MarketTimelineEvent, actor=None) -> MarketTimelineEvent:
    event.completed_at = utc_now()
    db.session.commit()
    record_market_audit(
        "market_timeline.completed",
        "market_timeline_event",
        event.id,
        actor=actor,
        after_state={"title": event.title, "market_id": event.market_id},
    )
    return event


def fetch_weather_snapshot(market: Market, actor=None) -> MarketWeatherSnapshot:
    if market.latitude is None or market.longitude is None:
        if not geocode_market_address(market, actor=actor):
            raise ValueError("Add a complete address and ZIP code before fetching Weather.gov data.")

    user_agent = current_app.config.get("WEATHER_USER_AGENT")
    headers = {"User-Agent": user_agent, "Accept": "application/geo+json"}
    with httpx.Client(headers=headers, timeout=10.0) as client:
        points_resp = client.get(
            f"https://api.weather.gov/points/{market.latitude:.4f},{market.longitude:.4f}"
        )
        points_resp.raise_for_status()
        forecast_url = points_resp.json()["properties"]["forecast"]
        forecast_resp = client.get(forecast_url)
        forecast_resp.raise_for_status()
        forecast_payload = forecast_resp.json()
        forecast_properties = forecast_payload.get("properties", {})
        fallback_url = forecast_properties.get("forecast")
        if not forecast_properties.get("periods") and fallback_url:
            fallback_resp = client.get(fallback_url)
            fallback_resp.raise_for_status()
            forecast_payload = fallback_resp.json()

    period = _select_weather_period(market, forecast_payload.get("properties", {}).get("periods", []))
    if period is None:
        periods = forecast_payload.get("properties", {}).get("periods", [])
        period = periods[0] if periods else {}

    snapshot = MarketWeatherSnapshot(
        market_id=market.id,
        provider="weather.gov",
        fetched_at=utc_now(),
        forecast_for=_parse_iso_datetime(period.get("startTime")),
        temperature=period.get("temperature"),
        short_forecast=period.get("shortForecast"),
        detailed_forecast=period.get("detailedForecast"),
        precipitation_probability=(period.get("probabilityOfPrecipitation") or {}).get("value"),
        wind_speed=period.get("windSpeed"),
        wind_direction=period.get("windDirection"),
        raw_payload=period,
    )
    db.session.add(snapshot)
    db.session.commit()
    record_market_audit(
        "market_weather.fetched",
        "market_weather_snapshot",
        snapshot.id,
        actor=actor,
        after_state={"market_id": market.id, "short_forecast": snapshot.short_forecast},
    )
    return snapshot


def save_market_document(
    *,
    market: Market,
    file: FileStorage,
    document_type: MarketDocumentType,
    notes: str | None = None,
    uploaded_by_user_id: int | None = None,
    actor=None,
) -> MarketDocument:
    if not file or not file.filename:
        raise ValueError("Choose a file to upload.")
    original_filename = secure_filename(file.filename)
    if not original_filename:
        raise ValueError("The uploaded file needs a valid filename.")
    content_type = file.mimetype or "application/octet-stream"
    if content_type not in ALLOWED_MARKET_DOCUMENT_TYPES:
        raise ValueError("That file type is not supported for market documents.")

    upload_dir = Path(current_app.config["MARKET_DOCUMENTS_PATH"]) / str(market.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}_{original_filename}"
    destination = upload_dir / stored_filename
    file.save(destination)
    storage_reference = upload_file_to_storage(
        destination,
        bucket=current_app.config.get("MARKET_DOCUMENTS_BUCKET", "markets"),
        key=f"{market.id}/{stored_filename}",
        local_root=current_app.config["MARKET_DOCUMENTS_PATH"],
        content_type=content_type or content_type_for_name(original_filename),
    )
    document = MarketDocument(
        market_id=market.id,
        original_filename=original_filename,
        stored_filename=storage_reference,
        content_type=content_type,
        file_size=destination.stat().st_size,
        document_type=document_type,
        notes=notes,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.session.add(document)
    db.session.commit()
    record_market_audit(
        "market_document.uploaded",
        "market_document",
        document.id,
        actor=actor,
        after_state={
            "market_id": market.id,
            "filename": document.original_filename,
            "document_type": document.document_type.value,
        },
    )
    return document


def market_document_path(document: MarketDocument) -> Path:
    stored = Path(document.stored_filename)
    if stored.is_absolute():
        return stored
    return Path(current_app.config["MARKET_DOCUMENTS_PATH"]) / str(document.market_id) / document.stored_filename


def record_market_audit(
    action: str,
    entity_type: str,
    entity_id: int | str | None,
    *,
    actor=None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    metadata: dict | None = None,
) -> None:
    get_audit_client().record(
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )


def _get_market_sales_total(market: Market) -> Decimal:
    result = db.session.query(func.sum(Order.total)).filter(
        Order.market_id == market.id,
        Order.deleted_at.is_(None),
    ).scalar()
    return result or Decimal(0)


def _market_address_query(market: Market) -> str | None:
    parts = [
        market.address,
        market.city,
        market.state,
        market.zip_code,
    ]
    query = ", ".join(part.strip() for part in parts if part and part.strip())
    return query or None


def _quick_stats(
    market: Market,
    packing_list: list[MarketPackingList],
    tasks: list[PrepTask],
    timeline_events: list[MarketTimelineEvent],
    documents: list[MarketDocument],
    performance: dict,
) -> dict:
    task_total = len(tasks)
    task_done = len([task for task in tasks if task.status == PrepTaskStatus.COMPLETED])
    marketing = [task for task in tasks if task.category == PrepTaskCategory.MARKETING]
    marketing_done = len([task for task in marketing if task.status == PrepTaskStatus.COMPLETED])
    planned = sum(item.planned_quantity or 0 for item in packing_list)
    packed = sum(item.packed_quantity or 0 for item in packing_list)
    sold = sum(item.sold_quantity or 0 for item in packing_list)
    application_steps = [
        market.application_submitted_at,
        market.application_approved_at,
        market.fee_paid_at,
    ]
    return {
        "task_total": task_total,
        "task_done": task_done,
        "task_pct": _count_pct(task_done, task_total),
        "marketing_total": len(marketing),
        "marketing_done": marketing_done,
        "marketing_pct": _count_pct(marketing_done, len(marketing)),
        "application_pct": _count_pct(len([step for step in application_steps if step]), len(application_steps)),
        "payment_pct": 100 if market.fee_paid_at else 0,
        "packing_pct": _count_pct(packed, planned),
        "planned_units": planned,
        "packed_units": packed,
        "sold_units": sold,
        "timeline_count": len(timeline_events),
        "document_count": len(documents),
        "net_position": performance["estimated_profit"],
    }


def _recent_activity(
    market: Market,
    tasks: list[PrepTask],
    timeline_events: list[MarketTimelineEvent],
    hotels: list[MarketHotelBooking],
    documents: list[MarketDocument],
    packing_list: list[MarketPackingList],
) -> list[dict]:
    rows = [{"label": "Market updated", "timestamp": market.updated_at, "detail": market.name}]
    rows.extend({"label": "Task updated", "timestamp": task.updated_at, "detail": task.title} for task in tasks)
    rows.extend({"label": "Timeline updated", "timestamp": item.updated_at, "detail": item.title} for item in timeline_events)
    rows.extend({"label": "Hotel updated", "timestamp": item.updated_at, "detail": item.hotel_name} for item in hotels)
    rows.extend({"label": "Document uploaded", "timestamp": item.created_at, "detail": item.original_filename} for item in documents)
    rows.extend(
        {
            "label": "Packing item updated",
            "timestamp": item.updated_at,
            "detail": item.product.name if item.product else f"Product #{item.product_id}",
        }
        for item in packing_list
    )
    return sorted(rows, key=lambda item: item["timestamp"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:8]


def _get_market_expenses_total(market: Market) -> Decimal:
    result = db.session.query(func.sum(Expense.amount)).filter(
        Expense.related_market_id == market.id
    ).scalar()
    return result or Decimal(0)


def _get_top_products(market: Market, limit: int = 5) -> list[dict]:
    from app.models import PosSaleItem, PosSaleItemType
    results = (
        db.session.query(
            PosSaleItem.description,
            func.sum(PosSaleItem.quantity).label("total_qty"),
            func.sum(PosSaleItem.line_total).label("total_revenue"),
        )
        .join(PosSale, PosSale.id == PosSaleItem.pos_sale_id)
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market.id,
            PosSession.status != PosSessionStatus.VOIDED,
            PosSaleItem.item_type == PosSaleItemType.PRODUCT,
        )
        .group_by(PosSaleItem.description)
        .order_by(func.sum(PosSaleItem.line_total).desc())
        .limit(limit)
        .all()
    )
    return [
        {"name": r[0], "quantity": int(r[1]), "revenue": Decimal(str(r[2])) if r[2] else Decimal(0)}
        for r in results
    ]


def _get_payment_methods(market: Market) -> list[dict]:
    results = (
        db.session.query(
            PosSale.payment_method,
            func.count(PosSale.id).label("count"),
            func.sum(PosSale.total).label("total"),
        )
        .join(PosSession, PosSession.id == PosSale.pos_session_id)
        .filter(
            PosSession.market_id == market.id,
            PosSession.status != PosSessionStatus.VOIDED,
        )
        .group_by(PosSale.payment_method)
        .all()
    )
    return [
        {"method": r[0] or "unknown", "count": int(r[1]), "total": Decimal(str(r[2])) if r[2] else Decimal(0)}
        for r in results
    ]


def _get_units_sold(market: Market) -> int:
    from app.models import PosSaleItem, PosSaleItemType
    result = db.session.query(func.sum(PosSaleItem.quantity)).join(
        PosSale, PosSale.id == PosSaleItem.pos_sale_id
    ).join(
        PosSession, PosSession.id == PosSale.pos_session_id
    ).filter(
        PosSession.market_id == market.id,
        PosSession.status != PosSessionStatus.VOIDED,
        PosSaleItem.item_type == PosSaleItemType.PRODUCT,
    ).scalar()
    return int(result or 0)


def _calc_pct(part: Decimal, total: Decimal) -> float | None:
    if total and total > 0:
        return float(part / total * 100)
    return None


def _count_pct(part: int, total: int) -> int:
    if not total:
        return 0
    return int(round(part / total * 100))


def _repeat_recommendation(
    *,
    revenue: Decimal,
    profit: Decimal,
    margin_percent: Decimal,
    units_sold: int,
    shrinkage_pct: float | None = None,
) -> dict[str, str]:
    if revenue <= Decimal("0.00"):
        return {
            "label": "Needs more data",
            "reason": "This market has not produced enough sales yet to judge whether it should be repeated.",
        }
    reasons: list[str] = []
    if shrinkage_pct is not None and shrinkage_pct > 10:
        reasons.append(f"Shrinkage is high at {shrinkage_pct}% — review packing and security.")
    if profit > Decimal("0.00") and margin_percent >= Decimal("25.00") and units_sold >= 10:
        if not reasons:
            return {
                "label": "Strong repeat candidate",
                "reason": "Profit, margin, and sell-through all cleared a healthy baseline.",
            }
        return {
            "label": "Repeat with caution",
            "reason": "Profit is healthy, but " + reasons[0].lower(),
        }
    if profit >= Decimal("0.00"):
        reason = "The market covered its costs, but the mix still needs tightening before the next booking."
        if reasons:
            reason += " " + reasons[0]
        return {"label": "Conditional repeat", "reason": reason}
    reason = "The market appears unprofitable after cost-of-goods and expenses. Review pricing, booth cost, and product mix first."
    if reasons:
        reason += " " + reasons[0]
    return {"label": "Review before repeating", "reason": reason}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _select_weather_period(market: Market, periods: list[dict]) -> dict | None:
    if not market.event_date:
        return periods[0] if periods else None
    for period in periods:
        starts_at = _parse_iso_datetime(period.get("startTime"))
        if starts_at and starts_at.date() == market.event_date:
            return period
    return None


def get_upcoming_markets(limit: int = 5) -> list[Market]:
    return Market.query.filter(
        Market.status.in_([MarketStatus.SCHEDULED])
    ).order_by(Market.event_date.asc()).limit(limit).all()
