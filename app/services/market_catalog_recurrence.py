from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

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


class RecurrencePattern(StrEnum):
    ONE_OFF = "one_off"
    FIXED_DAY_OF_MONTH = "fixed_day_of_month"
    NTH_WEEKDAY_OF_MONTH = "nth_weekday_of_month"
    WEEKLY = "weekly"


WEEKDAY_CHOICES = [
    ("MO", "Monday"),
    ("TU", "Tuesday"),
    ("WE", "Wednesday"),
    ("TH", "Thursday"),
    ("FR", "Friday"),
    ("SA", "Saturday"),
    ("SU", "Sunday"),
]


NTH_CHOICES = [
    (1, "1st"),
    (2, "2nd"),
    (3, "3rd"),
    (4, "4th"),
    (5, "5th"),
    (-1, "Last"),
]


MONTH_CHOICES = [
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]


def _normalize_rrule(rrule_str: str) -> str:
    """Strip the trailing ``Z`` from any UTC datetime values in the rule so the
    parsed rule stays in naive time (matches the naive datetimes callers pass
    to ``rrule.after()`` and avoids dateutil's "UNTIL must be in UTC" error).
    """
    import re

    return re.sub(r"=([0-9]{8}T[0-9]{6})Z\b", r"=\1", rrule_str)


def parse_rrule(rrule_str: str | None) -> rrule_mod.rrule | None:
    if not rrule_str or not rrule_str.strip():
        return None
    cleaned = rrule_str.strip()
    if cleaned.upper().startswith("RRULE:"):
        cleaned = cleaned[len("RRULE:") :]
    cleaned = _normalize_rrule(cleaned)
    # Always anchor on a fixed naive date so callers can safely use naive
    # ``datetime`` values with ``rrule.after()`` and so historic occurrences
    # are never silently dropped by dateutil's implicit ``dtstart=now`` rule.
    prefix = "DTSTART:19700101T000000\nRRULE:"
    try:
        return rrule_mod.rrulestr(prefix + cleaned)
    except ValueError, TypeError:
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
    until_raw = parts.get("UNTIL")

    month_names = {
        "1": "January",
        "2": "February",
        "3": "March",
        "4": "April",
        "5": "May",
        "6": "June",
        "7": "July",
        "8": "August",
        "9": "September",
        "10": "October",
        "11": "November",
        "12": "December",
    }
    weekday_names = {
        "MO": "Monday",
        "TU": "Tuesday",
        "WE": "Wednesday",
        "TH": "Thursday",
        "FR": "Friday",
        "SA": "Saturday",
        "SU": "Sunday",
    }
    ordinals = {
        1: "1st",
        2: "2nd",
        3: "3rd",
        4: "4th",
        5: "5th",
        -1: "Last",
    }

    def _until_clause() -> str:
        if not until_raw:
            return ""
        try:
            until_date = _parse_until(until_raw)
        except ValueError:
            return ""
        return f", through {until_date.strftime('%b %d, %Y')}"

    if freq_raw == "YEARLY" and bymonth and byday:
        month_name = month_names.get(bymonth, f"month {bymonth}")
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        if bysetpos:
            try:
                n = int(bysetpos)
            except ValueError:
                n = None
            ord_word = ordinals.get(n, bysetpos)
            cadence = "annually" if interval == 1 else f"every {interval} years"
            return f"{ord_word} {weekday_name} of {month_name}, {cadence}{_until_clause()}"
        cadence = "annually" if interval == 1 else f"every {interval} years"
        return f"{weekday_name} in {month_name}, {cadence}{_until_clause()}"

    if freq_raw == "YEARLY" and bymonth and bymonthday:
        month_name = month_names.get(bymonth, f"month {bymonth}")
        cadence = "annually" if interval == 1 else f"every {interval} years"
        return f"{month_name} {int(bymonthday)}, {cadence}{_until_clause()}"

    if freq_raw == "MONTHLY" and byday:
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        if bysetpos:
            try:
                n = int(bysetpos)
            except ValueError:
                n = None
            ord_word = ordinals.get(n, bysetpos)
            cadence = "monthly" if interval == 1 else f"every {interval} months"
            return f"{ord_word} {weekday_name} of each month, {cadence}{_until_clause()}"
        cadence = "monthly" if interval == 1 else f"every {interval} months"
        return f"{weekday_name} each month, {cadence}{_until_clause()}"

    if freq_raw == "MONTHLY" and bymonthday:
        cadence = "monthly" if interval == 1 else f"every {interval} months"
        return f"day {int(bymonthday)} of each month, {cadence}{_until_clause()}"

    if freq_raw == "WEEKLY" and byday:
        day_code = byday.lstrip("0123456789+-").upper()
        weekday_name = weekday_names.get(day_code, byday)
        month_window = ""
        if bymonth:
            nums = [int(m) for m in bymonth.split(",") if m]
            if nums:
                names = [month_names.get(str(n), str(n)) for n in nums]
                if len(names) == 1:
                    month_window = f" ({names[0]})"
                else:
                    month_window = f" ({names[0]}–{names[-1]})"
        cadence = ""
        if interval > 1:
            cadence = f", every {interval} weeks"
        return f"Every {weekday_name}{month_window}{cadence}{_until_clause()}"

    cadence = freq_word if interval == 1 else f"every {interval} {freq_word}"
    return cadence.capitalize() if interval == 1 else cadence


def _split_rrule_parts(rrule_str: str) -> dict[str, str]:
    cleaned = rrule_str.strip().upper()
    if cleaned.startswith("RRULE:"):
        cleaned = cleaned[len("RRULE:") :]
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


def _format_until(value: date) -> str:
    return value.strftime("%Y%m%dT235959Z")


def _parse_until(value: str) -> date:
    cleaned = value.strip().upper()
    if "T" in cleaned:
        cleaned = cleaned.split("T", 1)[0]
    return datetime.strptime(cleaned, "%Y%m%d").date()


def _validate_weekday(code: str | None) -> str | None:
    if code is None:
        return None
    upper = code.strip().upper()
    if upper not in WEEKDAY_CODES:
        raise ValueError(f"Unknown weekday code: {code}")
    return upper


def _month_range(start: int | None, end: int | None) -> str | None:
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError("Both start_month and end_month are required for a month window.")
    if not (1 <= start <= 12 and 1 <= end <= 12):
        raise ValueError("Month window values must be between 1 and 12.")
    if start <= end:
        months = list(range(start, end + 1))
    else:
        months = list(range(start, 13)) + list(range(1, end + 1))
    return ",".join(str(m) for m in months)


def build_rrule_from_wizard(
    pattern: str,
    *,
    weekday: str | None = None,
    nth: int | None = None,
    month: int | None = None,
    day_of_month: int | None = None,
    start_month: int | None = None,
    end_month: int | None = None,
    until_date: date | None = None,
    dtstart: date | None = None,
) -> tuple[str | None, date | None, str | None]:
    """Build an RRULE string from wizard inputs.

    Returns ``(rrule_str, dtstart_date, error_message)``. For one-off patterns
    the rrule is empty and the anchor date is returned instead.
    """
    try:
        pattern_enum = RecurrencePattern(pattern)
    except ValueError:
        return None, None, f"Unknown recurrence pattern: {pattern}"

    if pattern_enum == RecurrencePattern.ONE_OFF:
        if dtstart is None:
            return None, None, "A date is required for one-off markets."
        return None, dtstart, None

    if pattern_enum == RecurrencePattern.FIXED_DAY_OF_MONTH:
        if month is None or not (1 <= month <= 12):
            return None, None, "Pick a month for the fixed date."
        if day_of_month is None or not (1 <= day_of_month <= 31):
            return None, None, "Pick a day of the month."
        parts = [
            "FREQ=YEARLY",
            f"BYMONTH={int(month)}",
            f"BYMONTHDAY={int(day_of_month)}",
        ]
        if until_date:
            parts.append(f"UNTIL={_format_until(until_date)}")
        return ";".join(parts), dtstart, None

    if pattern_enum == RecurrencePattern.NTH_WEEKDAY_OF_MONTH:
        if month is None or not (1 <= month <= 12):
            return None, None, "Pick a month for the Nth weekday rule."
        if nth is None:
            return None, None, "Pick which occurrence (1st–5th or last)."
        try:
            day_code = _validate_weekday(weekday)
        except ValueError as exc:
            return None, None, str(exc)
        if day_code is None:
            return None, None, "Pick a weekday."
        parts = [
            "FREQ=YEARLY",
            f"BYMONTH={int(month)}",
            f"BYDAY={day_code}",
            f"BYSETPOS={int(nth)}",
        ]
        if until_date:
            parts.append(f"UNTIL={_format_until(until_date)}")
        return ";".join(parts), dtstart, None

    if pattern_enum == RecurrencePattern.WEEKLY:
        try:
            day_code = _validate_weekday(weekday)
        except ValueError as exc:
            return None, None, str(exc)
        if day_code is None:
            return None, None, "Pick a weekday."
        parts = ["FREQ=WEEKLY", f"BYDAY={day_code}"]
        try:
            month_window = _month_range(start_month, end_month)
        except ValueError as exc:
            return None, None, str(exc)
        if month_window:
            parts.append(f"BYMONTH={month_window}")
        if until_date:
            parts.append(f"UNTIL={_format_until(until_date)}")
        return ";".join(parts), dtstart, None

    return None, None, f"Unsupported pattern: {pattern}"


def _rule_with_dtstart(rrule_str: str, dtstart: date | None) -> rrule_mod.rrule | None:
    if not rrule_str:
        return None
    cleaned = rrule_str.strip()
    if cleaned.upper().startswith("RRULE:"):
        cleaned = cleaned[len("RRULE:") :]
    cleaned = _normalize_rrule(cleaned)
    # Default to a fixed early date so occurrences before "today" are not
    # silently dropped by dateutil's implicit dtstart=now behavior. The naive
    # DTSTART (without Z) keeps the rule in naive time to match the naive
    # datetimes callers pass to ``rrule.after()``.
    anchor = dtstart or date(1970, 1, 1)
    prefix = f"DTSTART:{anchor.strftime('%Y%m%d')}T000000\nRRULE:"
    try:
        return rrule_mod.rrulestr(prefix + cleaned)
    except ValueError, TypeError:
        return None


def next_two_occurrences(
    rrule_str: str | None,
    *,
    dtstart: date | None = None,
    today: date | None = None,
    count: int = 2,
) -> list[date]:
    """Return the next ``count`` occurrences strictly after ``today``.

    For YEARLY rules with a single annual occurrence (e.g. July 4, 3rd Sat of
    October) the result spans two consecutive years once today's date has
    passed the current year's occurrence. For weekly / monthly rules the next
    two occurrences are returned as soon as they happen.
    """
    if not rrule_str:
        return []
    rule = _rule_with_dtstart(rrule_str, dtstart)
    if rule is None:
        return []
    anchor = today or date.today()
    occurrences: list[date] = []
    cursor = datetime.combine(anchor, datetime.min.time())
    seen: set[date] = set()
    for _ in range(count * 4):
        nxt = rule.after(cursor, inc=False)
        if nxt is None:
            break
        d = nxt.date()
        if d in seen:
            break
        seen.add(d)
        occurrences.append(d)
        cursor = nxt
        if len(occurrences) >= count:
            break
    return occurrences[:count]


def wizard_summary(
    pattern: str,
    *,
    weekday: str | None = None,
    nth: int | None = None,
    month: int | None = None,
    day_of_month: int | None = None,
    start_month: int | None = None,
    end_month: int | None = None,
    until_date: date | None = None,
) -> str:
    """Return a human sentence describing what the wizard will build."""
    try:
        pattern_enum = RecurrencePattern(pattern)
    except ValueError:
        return ""

    month_names = {n: name for n, name in MONTH_CHOICES}
    weekday_names = {
        "MO": "Monday",
        "TU": "Tuesday",
        "WE": "Wednesday",
        "TH": "Thursday",
        "FR": "Friday",
        "SA": "Saturday",
        "SU": "Sunday",
    }
    ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", -1: "Last"}
    day_code = (weekday or "").strip().upper()
    weekday_name = weekday_names.get(day_code, day_code or "—")
    ord_word = ordinals.get(nth or 0, "—")
    month_name = month_names.get(month or 0, "—")

    if pattern_enum == RecurrencePattern.ONE_OFF:
        return "One-off market (no recurrence)."

    if pattern_enum == RecurrencePattern.FIXED_DAY_OF_MONTH:
        if month is None or day_of_month is None:
            return "Pick a month and day."
        suffix = "th"
        if day_of_month in (1, 21, 31):
            suffix = "st"
        elif day_of_month in (2, 22):
            suffix = "nd"
        elif day_of_month in (3, 23):
            suffix = "rd"
        until_clause = f" through {until_date.strftime('%b %d, %Y')}" if until_date else ""
        return f"{month_name} {day_of_month}{suffix}, annually{until_clause}."

    if pattern_enum == RecurrencePattern.NTH_WEEKDAY_OF_MONTH:
        if month is None or not day_code:
            return "Pick a month and weekday."
        until_clause = f" through {until_date.strftime('%b %d, %Y')}" if until_date else ""
        return f"{ord_word} {weekday_name} of {month_name}, annually{until_clause}."

    if pattern_enum == RecurrencePattern.WEEKLY:
        if not day_code:
            return "Pick a weekday."
        text = f"Every {weekday_name}"
        if start_month or end_month:
            start_name = month_names.get(start_month or 0)
            end_name = month_names.get(end_month or 0)
            if start_name and end_name:
                text += f" ({start_name}–{end_name})"
            elif start_name:
                text += f" (starting {start_name})"
        until_clause = f" through {until_date.strftime('%b %d, %Y')}" if until_date else ""
        return text + f"{until_clause}."

    return ""


def pattern_choices() -> list[tuple[str, str]]:
    return [
        (RecurrencePattern.ONE_OFF.value, "One-off date"),
        (RecurrencePattern.FIXED_DAY_OF_MONTH.value, "Fixed date (e.g. July 4)"),
        (
            RecurrencePattern.NTH_WEEKDAY_OF_MONTH.value,
            "Nth weekday (e.g. 3rd Saturday of October)",
        ),
        (RecurrencePattern.WEEKLY.value, "Weekly (e.g. every Saturday)"),
    ]


def split_rrule_parts(rrule_str: str | None) -> dict[str, str]:
    """Public wrapper around the private parser."""
    if not rrule_str:
        return {}
    return _split_rrule_parts(rrule_str)


def wizard_state_from_listing(
    rrule_str: str | None,
    anchor_date: date | None = None,
) -> dict:
    """Derive the full wizard payload (form field values) from a stored listing.

    Returns a dict suitable for setting on a bound ``MarketCatalogListingForm``
    instance, mapping form field names to their values. The caller is
    responsible for assigning each value to the corresponding ``form.field.data``.
    """
    state: dict = {
        "recurrence_pattern": RecurrencePattern.ONE_OFF.value,
        "recurrence_weekday": "",
        "recurrence_nth": None,
        "recurrence_month": None,
        "recurrence_day": None,
        "recurrence_start_month": None,
        "recurrence_end_month": None,
        "recurrence_until": None,
        "recurrence_anchor": anchor_date,
        "recurrence_limit_months": False,
    }
    parts = split_rrule_parts(rrule_str)
    freq = parts.get("FREQ")

    if not freq and anchor_date is not None:
        return state  # stays one_off

    if freq == "YEARLY" and parts.get("BYMONTH") and parts.get("BYMONTHDAY"):
        state["recurrence_pattern"] = RecurrencePattern.FIXED_DAY_OF_MONTH.value
        state["recurrence_month"] = int(parts["BYMONTH"])
        state["recurrence_day"] = int(parts["BYMONTHDAY"])
    elif freq == "YEARLY" and parts.get("BYMONTH") and parts.get("BYDAY") and parts.get("BYSETPOS"):
        state["recurrence_pattern"] = RecurrencePattern.NTH_WEEKDAY_OF_MONTH.value
        state["recurrence_month"] = int(parts["BYMONTH"])
        state["recurrence_nth"] = int(parts["BYSETPOS"])
        day_code = parts["BYDAY"].lstrip("0123456789+-").upper()
        state["recurrence_weekday"] = day_code
    elif freq == "WEEKLY" and parts.get("BYDAY"):
        state["recurrence_pattern"] = RecurrencePattern.WEEKLY.value
        day_code = parts["BYDAY"].lstrip("0123456789+-").upper()
        state["recurrence_weekday"] = day_code
        if parts.get("BYMONTH"):
            months = [int(m) for m in parts["BYMONTH"].split(",") if m]
            if months:
                state["recurrence_limit_months"] = True
                state["recurrence_start_month"] = months[0]
                state["recurrence_end_month"] = months[-1]
    # else: unsupported / unknown pattern. Leave as one_off so the wizard
    # defaults are shown; the advanced rrule field still carries the raw value.

    if parts.get("UNTIL"):
        cleaned = parts["UNTIL"]
        if "T" in cleaned:
            cleaned = cleaned.split("T", 1)[0]
        if len(cleaned) == 8:
            try:
                state["recurrence_until"] = datetime.strptime(cleaned, "%Y%m%d").date()
            except ValueError:
                state["recurrence_until"] = None

    return state
