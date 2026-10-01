"""The line that tells a lemon the date on its first turn of each day.

A harness gives a lemon the date when its session starts, and a session that runs
for days keeps that date. A day begins at `day_starts` local time (06:00 unless
configured), so a lemon working past midnight hears the date in the morning,
not at 12:05am. `seen` is a file per session holding the last day told; the
caller marks it only once the line has reached the lemon.
"""

import datetime as dt
from pathlib import Path

from .tmux import navigation


def seen_path(channel: str) -> Path:
    return navigation.get_state_path() / "date-line" / channel.replace(":", "-")


def _line(now: dt.datetime) -> str:
    return (
        f"It's {now.hour % 12 or 12}:{now.minute:02d}{'am' if now.hour < 12 else 'pm'} "
        f"{now:%A}, {now:%Y-%m-%d}."
    )


def _day(now: dt.datetime, day_starts: dt.time) -> str:
    since = dt.timedelta(
        hours=day_starts.hour, minutes=day_starts.minute, seconds=day_starts.second
    )
    return (now - since).date().isoformat()


def due(seen: Path, now: dt.datetime, day_starts: dt.time) -> str:
    """The line, or "" when `seen` already holds the day `now` falls in."""
    try:
        if seen.read_text() == _day(now, day_starts):
            return ""
    except FileNotFoundError:
        pass
    return _line(now)


def mark(seen: Path, now: dt.datetime, day_starts: dt.time) -> None:
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text(_day(now, day_starts))
