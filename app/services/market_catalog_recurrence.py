from __future__ import annotations

from datetime import date, datetime

from dateutil import rrule as rrule_mod


WEEKDAY_CODES = {
    "MO": rrule_mod.MO,
    "TU": rrule_mod.TU,
    "WE": rrule_mod.WE,
    "TH": rrule_mod.TH,
    "FR": rrule_mod.FR,
    "SA": rrule_mod.SA,
    "SU": rrule_mod.SU,
}

WEEKDAY_NAMES = {
    "monday": ("MO", rrule_mod.MO),
    "tuesday": ("TU", rrule_mod.TU),
    "wednesday": ("WE", rrule_mod.WE),
    "thursday": ("TH", rrule_mod.TH),
    "friday": ("FR", rrule_mod.FR),
    "saturday": ("SA", rrule_mod.SA),
    "sunday": ("SU", rrule_mod.SU),
}

FREQ_MAP = {
    "yearly": rrule_mod.YEARLY,
    "monthly": rrule_mod.MONTHLY,
    "weekly": rrule_mod.WEEKLY,
    "daily": rrule_mod.DAILY,
}

FREQ_NAMES = {
    rrule_mod.YEARLY: "YEARLY",
    rrule_mod.MONTHLY: "MONTHLY",
    rrule_mod.WEEKLY: "WEEKLY",
    rrule_mod.DAILY: "DAILY",
}


def parse_rrule(rrule_str: str | None) -> rrule_mod.rrule | None:
    if not rrule_str or not rrule_str.strip():
        return None
    try:
        return rrule_mod.rrulestr(rrule_str.strip())
    except (ValueError, TypeError):
        return None


def validate_rrule(rrule_str: str | None) -> tuple[bool, str | None]:
    if not rrule_str or not rrule_str.strip():
        return True, None
    parsed = parse_rrule(rrule_str)
    if parsed is None:
        return False, "Could not parse the RRULE string."
    return True, None


def next_occurrence(rrule_obj: rrule_mod.rrule, after_date: date | None = None) -> date | None:
    after_dt = _after_datetime(after_date)
    result = rrule_obj.after(after_dt, inc=False)
    if result is None:
        return None
    return result.date()


def next_occurrences(
    rrule_obj: rrule_mod.rrule, after_date: date | None = None, count: int = 4
) -> list[date]:
    if count <= 0:
        return []
    after_dt = _after_datetime(after_date)
    results: list[date] = []
    cursor = after_dt
    for _ in range(count):
        next_dt = rrule_obj.after(cursor, inc=False)
        if next_dt is None:
            break
        results.append(next_dt.date())
        cursor = next_dt
    return results


def build_rrule(
    frequency: str,
    *,
    month: int | None = None,
    day_of_month: int | None = None,
    weekday: str | None = None,
    week_number: int | None = None,
    interval: int = 1,
) -> str:
    freq = FREQ_MAP.get(frequency.lower())
    if freq is None:
        raise ValueError(f"Unknown frequency: {frequency}")

    parts: list[str] = [f"FREQ={FREQ_NAMES[freq]}", f"INTERVAL={max(interval, 1)}"]

    if month is not None:
        parts.append(f"BYMONTH={int(month)}")

    if day_of_month is not None:
        parts.append(f"BYMONTHDAY={int(day_of_month)}")

    if weekday is not None:
        code = weekday.upper()
        if code not in WEEKDAY_CODES:
            raise ValueError(f"Unknown weekday code: {weekday}")
        if week_number is not None:
            parts.append(f"BYDAY={code}")
            parts.append(f"BYSETPOS={int(week_number)}")
        else:
            parts.append(f"BYDAY={code}")

    return ";".join(parts)


def humanize_rrule(rrule_str: str | None) -> str:
    if not rrule_str or not rrule_str.strip():
        return "One-off / no recurrence"
    parsed = parse_rrule(rrule_str)
    if parsed is None:
        return rrule_str

    parts = _split_rrule_parts(rrule_str)
    freq_raw = parts.get("FREQ", "").upper()
    interval = int(parts.get("INTERVAL", "1") or "1")

    freq_word = {
        "YEARLY": "yearly",
        "MONTHLY": "monthly",
        "WEEKLY": "weekly",
        "DAILY": "daily",
    }.get(freq_raw, freq_raw.lower())

    bymonth = parts.get("BYMONTH")
    bymonthday = parts.get("BYMONTHDAY")
    byday = parts.get("BYDAY")
    bysetpos = parts.get("BYSETPOS")

    month_names = {
        "1": "January", "2": "February", "3": "March", "4": "April",
        "5": "May", "6": "June", "7": "July", "8": "August",
        "9": "September", "10": "October", "11": "November", "12": "December",
    }
    weekday_names = {
        "MO": "Monday", "TU": "Tuesday", "WE": "Wednesday", "TH": "Thursday",
        "FR": "Friday", "SA": "Saturday", "SU": "Sunday",
    }
    ordinals = {
        1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th",
    }

    if freq_raw == "YEARLY" and bymonth and byday:
        month_name = month_names.get(bymonth, f"month {bymonth}")
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        if bysetpos and bysetpos.isdigit():
            n = int(bysetpos)
            ord_word = ordinals.get(n, f"{n}th")
            cadence = "annually" if interval == 1 else f"every {interval} years"
            return f"{ord_word} {weekday_name} of {month_name}, {cadence}"
        cadence = "annually" if interval == 1 else f"every {interval} years"
        return f"{weekday_name} in {month_name}, {cadence}"

    if freq_raw == "YEARLY" and bymonth and bymonthday:
        month_name = month_names.get(bymonth, f"month {bymonth}")
        cadence = "annually" if interval == 1 else f"every {interval} years"
        return f"{month_name} {int(bymonthday)}, {cadence}"

    if freq_raw == "MONTHLY" and byday:
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        if bysetpos and bysetpos.isdigit():
            n = int(bysetpos)
            ord_word = ordinals.get(n, f"{n}th")
            cadence = "monthly" if interval == 1 else f"every {interval} months"
            return f"{ord_word} {weekday_name} of each month, {cadence}"
        cadence = "monthly" if interval == 1 else f"every {interval} months"
        return f"{weekday_name} each month, {cadence}"

    if freq_raw == "MONTHLY" and bymonthday:
        cadence = "monthly" if interval == 1 else f"every {interval} months"
        return f"day {int(bymonthday)} of each month, {cadence}"

    if freq_raw == "WEEKLY" and byday:
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        cadence = "weekly" if interval == 1 else f"every {interval} weeks"
        return f"{weekday_name} {cadence}"

    cadence = freq_word if interval == 1 else f"every {interval} {freq_word}"
    return cadence.capitalize() if interval == 1 else cadence


def _split_rrule_parts(rrule_str: str) -> dict[str, str]:
    cleaned = rrule_str.strip().upper()
    if cleaned.startswith("RRULE:"):
        cleaned = cleaned[len("RRULE:"):]
    parts: dict[str, str] = {}
    for token in cleaned.split(";"):
        if "=" in token:
            key, value = token.split("=", 1)
            parts[key] = value
    return parts


def _after_datetime(after_date: date | None) -> datetime:
    if after_date is None:
        return datetime.now()
    return datetime.combine(after_date, datetime.min.time())