from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from flask import request
from flask_login import current_user

from app.extensions import db
from app.models import Business


UTC = ZoneInfo("UTC")

FMT_DATE = "%Y-%m-%d"
FMT_DATETIME = "%Y-%m-%d %H:%M"
FMT_DATETIME_FULL = "%B %d, %Y at %H:%M"
FMT_TIME = "%H:%M"
FMT_MONTH_DAY_YEAR = "%B %d, %Y"
FMT_MONTH_DAY = "%b %d, %Y"
FMT_MONTH_DAY_TIME = "%b %d, %-I:%M %p"
FMT_TIME_AMPM = "%-I:%M %p"


def get_user_timezone() -> str:
    tz_from_cookie = request.cookies.get("tz", "")
    if tz_from_cookie:
        try:
            ZoneInfo(tz_from_cookie)
            return tz_from_cookie
        except (KeyError, TypeError):
            pass
    try:
        if current_user.is_authenticated and current_user.business_id:
            business = db.session.get(Business, current_user.business_id)
            if business and business.timezone:
                return business.timezone
    except Exception:
        pass
    try:
        business = db.session.query(Business).filter(Business.is_active == True).first()
        if business and business.timezone:
            return business.timezone
    except Exception:
        pass
    return "America/Chicago"


Dt = datetime | date


def to_local(dt: Dt | None, tz_name: str = "") -> Dt | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    if not tz_name:
        try:
            tz_name = get_user_timezone()
        except Exception:
            tz_name = "America/Chicago"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    try:
        return dt.astimezone(ZoneInfo(tz_name))
    except (KeyError, TypeError):
        return dt.astimezone(ZoneInfo("America/Chicago"))


def format_local(dt: Dt | None, fmt: str = FMT_DATETIME, tz_name: str = "") -> str:
    if dt is None:
        return ""
    local_dt = to_local(dt, tz_name)
    if local_dt is None:
        return ""
    return local_dt.strftime(fmt)


def register_template_filters(app: Any) -> None:
    @app.template_filter("local_datetime")
    def _local_datetime(dt: Dt | None, fmt: str = FMT_DATETIME) -> str:
        return format_local(dt, fmt)

    @app.template_filter("local_date")
    def _local_date(dt: Dt | None) -> str:
        return format_local(dt, FMT_DATE)

    @app.template_filter("local_time")
    def _local_time(dt: Dt | None) -> str:
        return format_local(dt, FMT_TIME)

    @app.template_filter("local_full")
    def _local_full(dt: Dt | None) -> str:
        return format_local(dt, FMT_DATETIME_FULL)

    @app.template_global("now_local")
    def _now_local() -> str:
        return format_local(datetime.now(UTC))
