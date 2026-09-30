"""Tests for snooze duration parsing and wake-time formatting."""

from datetime import datetime

from lemonaid.inbox.snooze_time import next_morning, parse_duration, parse_wake
from lemonaid.inbox.tui.screens import format_wake_time


def test_parse_bare_number_is_minutes():
    assert parse_duration("45") == 45 * 60


def test_parse_units():
    assert parse_duration("30m") == 30 * 60
    assert parse_duration("2h") == 2 * 3600
    assert parse_duration("3d") == 3 * 86400


def test_parse_is_forgiving_about_whitespace_and_case():
    assert parse_duration("  2H  ") == 2 * 3600


def test_parse_accepts_fractional():
    assert parse_duration("1.5h") == 5400


def test_parse_rejects_nonsense():
    for bad in ("", "   ", "soon", "m", "-5m", "0", "0h", "inf", "1e309h", "nan"):
        assert parse_duration(bad) is None, bad


def test_next_morning_same_day_when_before_nine():
    now = datetime(2026, 7, 30, 6, 30).timestamp()
    target = datetime.fromtimestamp(next_morning(now))
    assert (target.month, target.day, target.hour, target.minute) == (7, 30, 9, 0)


def test_next_morning_rolls_over_when_after_nine():
    now = datetime(2026, 7, 30, 14, 0).timestamp()
    target = datetime.fromtimestamp(next_morning(now))
    assert (target.month, target.day, target.hour) == (7, 31, 9)


def test_next_morning_is_strictly_future_at_exactly_nine():
    now = datetime(2026, 7, 30, 9, 0).timestamp()
    target = datetime.fromtimestamp(next_morning(now))
    assert target.day == 31


def test_parse_wake_morning_is_the_next_nine_am():
    now = datetime(2026, 7, 30, 14, 0).timestamp()
    assert parse_wake(" Morning ", now) == next_morning(now)


def test_parse_wake_duration_counts_from_now():
    assert parse_wake("2h", 1000.0) == 1000.0 + 7200
    assert parse_wake("soon", 1000.0) is None


def test_parse_wake_refuses_a_time_past_any_date():
    assert parse_wake("1e300d", 1000.0) is None


def test_format_wake_time_today_is_clock_only():
    now = datetime(2026, 7, 30, 8, 0).timestamp()
    until = datetime(2026, 7, 30, 14, 30).timestamp()
    assert format_wake_time(until, now) == "14:30"


def test_format_wake_time_other_day_includes_weekday():
    now = datetime(2026, 7, 30, 8, 0).timestamp()
    until = datetime(2026, 7, 31, 9, 0).timestamp()
    assert format_wake_time(until, now) == "Fri 09:00"
