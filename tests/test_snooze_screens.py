"""Tests for snooze duration parsing, wake-time formatting, and the snooze picker."""

import asyncio
import time
from datetime import datetime

from textual.app import App

from lemonaid.inbox.snooze_time import next_morning, parse_duration, parse_wake
from lemonaid.inbox.tui.screens import SnoozeScreen, format_wake_time

NINE = datetime(2026, 1, 1, 9).time()


def test_parse_bare_number_is_minutes():
    assert parse_duration("45") == 45 * 60


def test_parse_units():
    assert parse_duration("30m") == 30 * 60
    assert parse_duration("2h") == 2 * 3600
    assert parse_duration("3d") == 3 * 86400
    assert parse_duration("1w") == 7 * 86400


def test_parse_is_forgiving_about_whitespace_and_case():
    assert parse_duration("  2H  ") == 2 * 3600


def test_parse_accepts_fractional():
    assert parse_duration("1.5h") == 5400


def test_parse_rejects_nonsense():
    for bad in ("", "   ", "soon", "m", "-5m", "0", "0h", "inf", "1e309h", "nan"):
        assert parse_duration(bad) is None, bad


def test_next_morning_same_day_when_before_nine():
    now = datetime(2026, 7, 30, 6, 30).timestamp()
    target = datetime.fromtimestamp(next_morning(now, NINE))
    assert (target.month, target.day, target.hour, target.minute) == (7, 30, 9, 0)


def test_next_morning_rolls_over_when_after_nine():
    now = datetime(2026, 7, 30, 14, 0).timestamp()
    target = datetime.fromtimestamp(next_morning(now, NINE))
    assert (target.month, target.day, target.hour) == (7, 31, 9)


def test_next_morning_is_strictly_future_at_exactly_nine():
    now = datetime(2026, 7, 30, 9, 0).timestamp()
    target = datetime.fromtimestamp(next_morning(now, NINE))
    assert target.day == 31


def test_parse_wake_morning_is_the_next_nine_am():
    now = datetime(2026, 7, 30, 14, 0).timestamp()
    assert parse_wake(" Morning ", now, NINE) == next_morning(now, NINE)


def test_parse_wake_duration_counts_from_now():
    assert parse_wake("2h", 1000.0, NINE) == 1000.0 + 7200
    assert parse_wake("soon", 1000.0, NINE) is None


def test_parse_wake_refuses_a_time_past_any_date():
    assert parse_wake("1e300d", 1000.0, NINE) is None


def test_format_wake_time_today_is_clock_only():
    now = datetime(2026, 7, 30, 8, 0).timestamp()
    until = datetime(2026, 7, 30, 14, 30).timestamp()
    assert format_wake_time(until, now) == "14:30"


def test_format_wake_time_other_day_includes_weekday():
    now = datetime(2026, 7, 30, 8, 0).timestamp()
    until = datetime(2026, 7, 31, 9, 0).timestamp()
    assert format_wake_time(until, now) == "Fri 09:00"


def _picked(keys: list[str]) -> list[float | None]:
    picked: list[float | None] = []

    async def run() -> None:
        app = App()
        async with app.run_test() as pilot:
            app.push_screen(SnoozeScreen(), picked.append)
            await pilot.pause()
            await pilot.press(*keys)
            await pilot.pause()

    asyncio.run(run())
    return picked


def test_the_picker_takes_a_typed_duration_without_choosing_custom_first():
    before = time.time()
    [until] = _picked(["4", "5", "m", "enter"])
    assert until is not None
    assert before + 45 * 60 <= until <= time.time() + 45 * 60


def test_enter_on_an_empty_box_takes_the_highlighted_preset():
    before = time.time()
    [first] = _picked(["enter"])
    [third] = _picked(["down", "down", "enter"])
    assert first is not None and third is not None
    assert before + 30 * 60 <= first <= time.time() + 30 * 60
    assert third == next_morning(time.time(), NINE)


def test_up_from_the_first_preset_wraps_to_the_last():
    [until] = _picked(["up", "enter"])
    assert until == parse_wake("4d", time.time(), NINE)


def test_nonsense_keeps_the_picker_open():
    assert _picked(["s", "o", "o", "n", "enter"]) == []
