"""When a snooze ends: the syntax the TUI's snooze picker and `inbox snooze` share.

A snooze given in days or weeks, of at least a day, ends at the start of the day
it reaches (`[inbox] snooze_day_starts`), not exactly that many hours later.
"""

import math
import typing as ty
from datetime import datetime, time, timedelta

DEFAULT_DAY_START: ty.Final = time(9, 0)
DEFAULT_PRESETS: ty.Final = ("30m", "3h", "1d", "4d")

SYNTAX: ty.Final = "a duration like 45m, 2h, 3d or 1w, or 'morning'"

_UNITS: ty.Final = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}
_UNIT_NAMES: ty.Final = {"m": "minute", "h": "hour", "d": "day", "w": "week"}
_DAY: ty.Final = 86400


def next_morning(now: float, day_start: time) -> float:
    """The next `day_start` strictly after `now`."""
    dt = datetime.fromtimestamp(now)
    target = datetime.combine(dt.date(), day_start)
    if target <= dt:
        target += timedelta(days=1)

    return target.timestamp()


def _split(text: str) -> tuple[float, str] | None:
    """A duration's number and unit; a bare number is minutes."""
    text = text.strip().lower()
    if not text:
        return None

    unit = text[-1] if text[-1] in _UNITS else "m"
    try:
        value = float(text[:-1] if text[-1] in _UNITS else text)
    except ValueError:
        return None

    return (value, unit) if value > 0 and math.isfinite(value) else None


def parse_duration(text: str) -> float | None:
    """Parse a relative duration like '45m', '2h', '3d', '1w' into seconds.

    None if unparseable, infinite, or not positive, which the caller surfaces
    rather than snoozing by accident.
    """
    split = _split(text)
    return split[0] * _UNITS[split[1]] if split else None


def _mornings(value: float, unit: str) -> int:
    """How many starts of day a duration counts, or 0 for one under a day (kept exact)."""
    days = value * _UNITS[unit] / _DAY
    return math.ceil(days) if unit in ("d", "w") and days >= 1 else 0


def parse_wake(text: str, now: float, day_start: time) -> float | None:
    """The wake time *text* names, or None when it names none or one too far off.

    A day or more, in days or weeks, counts mornings: `Nd` ends at the Nth
    `day_start` strictly after *now*, so '1d' at 02:00 wakes at 09:00 that day.
    A fraction of a day rounds up, and 'morning' is '1d'. Minutes, hours, and
    anything under a day are exact.
    """
    split = (1.0, "d") if text.strip().lower() == "morning" else _split(text)
    if split is None:
        return None

    try:
        mornings = _mornings(*split)
        if mornings:
            first = datetime.fromtimestamp(next_morning(now, day_start))
            return datetime.combine(
                first.date() + timedelta(days=mornings - 1), day_start
            ).timestamp()

        exact = now + split[0] * _UNITS[split[1]]
        datetime.fromtimestamp(exact)  # raises when no date is that far off
        return exact
    except (OverflowError, OSError, ValueError):
        return None


def describe(text: str, now: float, day_start: time) -> str:
    """A preset's label: '30 minutes', 'Tomorrow morning, Sat 09:00', '4 days, Tue 09:00'."""
    wake = parse_wake(text, now, day_start)
    split = (1.0, "d") if text.strip().lower() == "morning" else _split(text)
    if wake is None or split is None:
        return text.strip()

    value, unit = split
    amount = f"{value:g} {_UNIT_NAMES[unit]}{'' if value == 1 else 's'}"
    if not _mornings(value, unit):
        return amount

    when = f"{datetime.fromtimestamp(wake):%a %H:%M}"
    days_on = (datetime.fromtimestamp(wake).date() - datetime.fromtimestamp(now).date()).days
    if value == 1 and unit == "d":
        return f"{'This' if days_on == 0 else 'Tomorrow'} morning, {when}"

    return f"{amount}, {when}"
