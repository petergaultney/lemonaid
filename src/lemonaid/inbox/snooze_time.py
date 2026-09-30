"""When a snooze ends: the syntax the TUI's snooze picker and `inbox snooze` share."""

import math
import typing as ty
from datetime import datetime, timedelta

_MORNING_HOUR: ty.Final = 9

SYNTAX: ty.Final = "a duration like 45m, 2h, or 3d, or 'morning'"


def next_morning(now: float) -> float:
    """The next 9am strictly after `now`."""
    dt = datetime.fromtimestamp(now)
    target = dt.replace(hour=_MORNING_HOUR, minute=0, second=0, microsecond=0)
    if target <= dt:
        target += timedelta(days=1)

    return target.timestamp()


def parse_duration(text: str) -> float | None:
    """Parse a relative duration like '45m', '2h', '3d' into seconds.

    A bare number is read as minutes. Returns None if unparseable, infinite, or not
    positive, which the caller surfaces rather than snoozing by accident.
    """
    text = text.strip().lower()
    if not text:
        return None

    units = {"m": 60, "h": 3600, "d": 86400}
    multiplier = 60
    if text[-1] in units:
        multiplier = units[text[-1]]
        text = text[:-1]

    try:
        value = float(text)
    except ValueError:
        return None

    return value * multiplier if value > 0 and math.isfinite(value) else None


def parse_wake(text: str, now: float) -> float | None:
    """The wake time *text* names: 'morning' (the next 9am) or a duration from *now*.

    None when it names none, or one too far off to be a date.
    """
    if text.strip().lower() == "morning":
        return next_morning(now)

    seconds = parse_duration(text)
    if seconds is None:
        return None

    try:
        datetime.fromtimestamp(now + seconds)
    except (OverflowError, OSError, ValueError):
        return None

    return now + seconds
