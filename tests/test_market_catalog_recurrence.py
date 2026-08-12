from __future__ import annotations

from datetime import date

from app.services.market_catalog_recurrence import (
    build_rrule,
    build_rrule_from_wizard,
    humanize_rrule,
    next_occurrence,
    next_occurrences,
    next_two_occurrences,
    parse_rrule,
    validate_rrule,
    wizard_state_from_listing,
    wizard_summary,
)


def test_build_rrule_yearly_nth_weekday_of_month():
    rrule_str = build_rrule("yearly", month=10, weekday="SA", week_number=3)
    assert "FREQ=YEARLY" in rrule_str
    assert "BYMONTH=10" in rrule_str
    assert "BYDAY=SA" in rrule_str
    assert "BYSETPOS=3" in rrule_str


def test_build_rrule_yearly_fixed_date():
    rrule_str = build_rrule("yearly", month=7, day_of_month=4)
    assert "FREQ=YEARLY" in rrule_str
    assert "BYMONTH=7" in rrule_str
    assert "BYMONTHDAY=4" in rrule_str


def test_build_rrule_monthly_first_sunday():
    rrule_str = build_rrule("monthly", weekday="SU", week_number=1)
    assert "FREQ=MONTHLY" in rrule_str
    assert "BYDAY=SU" in rrule_str
    assert "BYSETPOS=1" in rrule_str


def test_next_occurrence_3rd_saturday_october():
    rrule_str = build_rrule("yearly", month=10, weekday="SA", week_number=3)
    rrule_obj = parse_rrule(rrule_str)
    assert rrule_obj is not None
    # From August 2026, the next 3rd Saturday of October is Oct 17, 2026.
    result = next_occurrence(rrule_obj, date(2026, 8, 10))
    assert result == date(2026, 10, 17)


def test_next_occurrences_july_4th_returns_consecutive_years():
    rrule_str = build_rrule("yearly", month=7, day_of_month=4)
    rrule_obj = parse_rrule(rrule_str)
    occurrences = next_occurrences(rrule_obj, date(2026, 8, 10), count=4)
    assert occurrences == [
        date(2027, 7, 4),
        date(2028, 7, 4),
        date(2029, 7, 4),
        date(2030, 7, 4),
    ]


def test_next_occurrences_monthly_first_sunday():
    rrule_str = build_rrule("monthly", weekday="SU", week_number=1)
    rrule_obj = parse_rrule(rrule_str)
    occurrences = next_occurrences(rrule_obj, date(2026, 8, 10), count=3)
    assert occurrences == [date(2026, 9, 6), date(2026, 10, 4), date(2026, 11, 1)]


def test_parse_rrule_none_returns_none():
    assert parse_rrule(None) is None
    assert parse_rrule("") is None


def test_parse_rrule_invalid_returns_none():
    assert parse_rrule("FREQ=BOGUS") is None


def test_validate_rrule_empty_is_valid():
    ok, error = validate_rrule("")
    assert ok is True
    assert error is None


def test_validate_rrule_bad_returns_error():
    ok, error = validate_rrule("FREQ=BOGUS")
    assert ok is False
    assert error is not None


def test_validate_rrule_good_is_valid():
    ok, error = validate_rrule(build_rrule("yearly", month=7, day_of_month=4))
    assert ok is True
    assert error is None


def test_humanize_rrule_3rd_saturday_october():
    rrule_str = build_rrule("yearly", month=10, weekday="SA", week_number=3)
    assert humanize_rrule(rrule_str) == "3rd Saturday of October, annually"


def test_humanize_rrule_july_4th():
    rrule_str = build_rrule("yearly", month=7, day_of_month=4)
    assert humanize_rrule(rrule_str) == "July 4, annually"


def test_humanize_rrule_monthly_first_sunday():
    rrule_str = build_rrule("monthly", weekday="SU", week_number=1)
    assert humanize_rrule(rrule_str) == "1st Sunday of each month, monthly"


def test_humanize_rrule_none():
    assert humanize_rrule(None) == "One-off / no recurrence"
    assert humanize_rrule("") == "One-off / no recurrence"


# ---------------------------------------------------------------------------
# Wizard builder
# ---------------------------------------------------------------------------


def test_wizard_one_off_returns_no_rrule():
    rrule, dtstart, error = build_rrule_from_wizard("one_off", dtstart=date(2026, 7, 4))
    assert error is None
    assert rrule is None
    assert dtstart == date(2026, 7, 4)


def test_wizard_one_off_requires_date():
    rrule, dtstart, error = build_rrule_from_wizard("one_off")
    assert rrule is None
    assert error is not None


def test_wizard_fixed_day_of_month():
    rrule, dtstart, error = build_rrule_from_wizard("fixed_day_of_month", month=7, day_of_month=4)
    assert error is None
    assert rrule == "FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4"


def test_wizard_fixed_day_of_month_with_until():
    rrule, dtstart, error = build_rrule_from_wizard(
        "fixed_day_of_month", month=7, day_of_month=4, until_date=date(2027, 10, 31)
    )
    assert error is None
    assert rrule == "FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4;UNTIL=20271031T235959Z"


def test_wizard_fixed_day_requires_day():
    rrule, dtstart, error = build_rrule_from_wizard("fixed_day_of_month", month=7)
    assert rrule is None
    assert error is not None


def test_wizard_nth_weekday_of_month():
    rrule, dtstart, error = build_rrule_from_wizard(
        "nth_weekday_of_month", month=6, weekday="MO", nth=5
    )
    assert error is None
    assert rrule == "FREQ=YEARLY;BYMONTH=6;BYDAY=MO;BYSETPOS=5"


def test_wizard_nth_weekday_last():
    rrule, dtstart, error = build_rrule_from_wizard(
        "nth_weekday_of_month", month=11, weekday="FR", nth=-1
    )
    assert error is None
    assert rrule == "FREQ=YEARLY;BYMONTH=11;BYDAY=FR;BYSETPOS=-1"


def test_wizard_nth_weekday_requires_weekday():
    rrule, dtstart, error = build_rrule_from_wizard("nth_weekday_of_month", month=6, nth=5)
    assert rrule is None
    assert error is not None


def test_wizard_weekly():
    rrule, dtstart, error = build_rrule_from_wizard("weekly", weekday="SA")
    assert error is None
    assert rrule == "FREQ=WEEKLY;BYDAY=SA"


def test_wizard_weekly_with_month_window():
    rrule, dtstart, error = build_rrule_from_wizard(
        "weekly", weekday="SA", start_month=3, end_month=10
    )
    assert error is None
    assert rrule == "FREQ=WEEKLY;BYDAY=SA;BYMONTH=3,4,5,6,7,8,9,10"


def test_wizard_weekly_month_window_wraps_year():
    rrule, dtstart, error = build_rrule_from_wizard(
        "weekly", weekday="SA", start_month=11, end_month=2
    )
    assert error is None
    assert rrule == "FREQ=WEEKLY;BYDAY=SA;BYMONTH=11,12,1,2"


def test_wizard_weekly_requires_weekday():
    rrule, dtstart, error = build_rrule_from_wizard("weekly")
    assert rrule is None
    assert error is not None


def test_wizard_bad_pattern():
    rrule, dtstart, error = build_rrule_from_wizard("bogus")
    assert rrule is None
    assert error is not None


def test_wizard_bad_weekday():
    rrule, dtstart, error = build_rrule_from_wizard("weekly", weekday="XX")
    assert rrule is None
    assert error is not None


# ---------------------------------------------------------------------------
# Next-two preview
# ---------------------------------------------------------------------------


def test_next_two_july_4_past_this_year_skips_to_next_two_years():
    rrule, _, _ = build_rrule_from_wizard("fixed_day_of_month", month=7, day_of_month=4)
    results = next_two_occurrences(rrule, today=date(2026, 8, 10))
    assert results == [date(2027, 7, 4), date(2028, 7, 4)]


def test_next_two_july_4_future_this_year():
    rrule, _, _ = build_rrule_from_wizard("fixed_day_of_month", month=7, day_of_month=4)
    results = next_two_occurrences(rrule, today=date(2026, 3, 10))
    assert results == [date(2026, 7, 4), date(2027, 7, 4)]


def test_next_two_3rd_saturday_october():
    rrule, _, _ = build_rrule_from_wizard("nth_weekday_of_month", month=10, weekday="SA", nth=3)
    results = next_two_occurrences(rrule, today=date(2026, 8, 10))
    assert results == [date(2026, 10, 17), date(2027, 10, 16)]


def test_next_two_5th_monday_june_skips_years_without_fifth():
    # June only has a 5th Monday in some years; RRULE semantics skip the rest.
    rrule, _, _ = build_rrule_from_wizard("nth_weekday_of_month", month=6, weekday="MO", nth=5)
    results = next_two_occurrences(rrule, today=date(2026, 1, 1))
    assert results == [date(2026, 6, 29), date(2031, 6, 30)]


def test_next_two_weekly():
    rrule, _, _ = build_rrule_from_wizard("weekly", weekday="SA")
    results = next_two_occurrences(rrule, today=date(2026, 7, 3))
    assert results == [date(2026, 7, 4), date(2026, 7, 11)]


def test_next_two_weekly_month_window():
    rrule, _, _ = build_rrule_from_wizard("weekly", weekday="SA", start_month=3, end_month=10)
    results = next_two_occurrences(rrule, today=date(2026, 10, 30))
    assert results == [date(2026, 10, 31), date(2027, 3, 6)]


def test_next_two_empty_returns_empty():
    assert next_two_occurrences(None) == []
    assert next_two_occurrences("") == []


# ---------------------------------------------------------------------------
# Wizard summary
# ---------------------------------------------------------------------------


def test_wizard_summary_fixed_day():
    text = wizard_summary("fixed_day_of_month", month=7, day_of_month=4)
    assert text == "July 4th, annually."


def test_wizard_summary_nth_weekday():
    text = wizard_summary("nth_weekday_of_month", month=6, weekday="MO", nth=5)
    assert text == "5th Monday of June, annually."


def test_wizard_summary_weekly():
    text = wizard_summary("weekly", weekday="SA")
    assert text == "Every Saturday."


def test_wizard_summary_weekly_month_window():
    text = wizard_summary("weekly", weekday="SA", start_month=3, end_month=10)
    assert text == "Every Saturday (March–October)."


# ---------------------------------------------------------------------------
# wizard_state_from_listing
# ---------------------------------------------------------------------------


def test_wizard_state_from_listing_one_off():
    state = wizard_state_from_listing(None, anchor_date=date(2026, 7, 4))
    assert state["recurrence_pattern"] == "one_off"
    assert state["recurrence_anchor"] == date(2026, 7, 4)


def test_wizard_state_from_listing_fixed():
    state = wizard_state_from_listing("FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4")
    assert state["recurrence_pattern"] == "fixed_day_of_month"
    assert state["recurrence_month"] == 7
    assert state["recurrence_day"] == 4


def test_wizard_state_from_listing_nth():
    state = wizard_state_from_listing("FREQ=YEARLY;BYMONTH=10;BYDAY=SA;BYSETPOS=3")
    assert state["recurrence_pattern"] == "nth_weekday_of_month"
    assert state["recurrence_month"] == 10
    assert state["recurrence_nth"] == 3
    assert state["recurrence_weekday"] == "SA"


def test_wizard_state_from_listing_weekly_window():
    state = wizard_state_from_listing("FREQ=WEEKLY;BYDAY=SA;BYMONTH=3,4,5,6,7,8,9,10")
    assert state["recurrence_pattern"] == "weekly"
    assert state["recurrence_weekday"] == "SA"
    assert state["recurrence_limit_months"] is True
    assert state["recurrence_start_month"] == 3
    assert state["recurrence_end_month"] == 10


def test_wizard_state_from_listing_with_until():
    state = wizard_state_from_listing("FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4;UNTIL=20271031T235959Z")
    assert state["recurrence_until"] == date(2027, 10, 31)


def test_wizard_state_from_listing_unsupported():
    state = wizard_state_from_listing("FREQ=MONTHLY;INTERVAL=2")
    assert state["recurrence_pattern"] == "one_off"


# ---------------------------------------------------------------------------
# humanize_rrule weekly wording
# ---------------------------------------------------------------------------


def test_humanize_rrule_weekly_plain():
    assert humanize_rrule("FREQ=WEEKLY;BYDAY=SA") == "Every Saturday"


def test_humanize_rrule_weekly_with_month_window():
    text = humanize_rrule("FREQ=WEEKLY;BYDAY=SA;BYMONTH=3,4,5,6,7,8,9,10")
    assert text == "Every Saturday (March–October)"


def test_humanize_rrule_weekly_with_until():
    text = humanize_rrule("FREQ=WEEKLY;BYDAY=SA;BYMONTH=3,4,5,6,7,8,9,10;UNTIL=20261031T235959Z")
    assert "Oct 31, 2026" in text
