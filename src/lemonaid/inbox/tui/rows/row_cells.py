"""The time and name cells of an inbox row."""

import time
from collections import abc
from datetime import datetime

from rich.style import Style
from rich.text import Text

from ... import db
from ..utils import styled_cell
from . import pr_numbers

_DAY_SECONDS = 86400


def format_timestamp(ts: float) -> str:
    """The clock time for today and yesterday, a date for anything older.

    Yesterday keeps a time because it is still the recent past - what you want
    from a row from last night is the hour, not the date. It is prefixed `y`
    so the hour is not read as today's: a bare 23:59 at breakfast says nothing
    about which night it was.

    Only past that does the clock stop being the useful part and the calendar
    day take over.
    """
    dt = datetime.fromtimestamp(ts)
    days_ago = (datetime.now().date() - dt.date()).days
    if days_ago == 0:
        return dt.strftime("%H:%M:%S")

    if days_ago == 1:
        return f"y {dt.strftime('%H:%M')}"

    return dt.strftime("%Y-%m-%d")


def time_cell(
    ts: float, is_unread: bool, *, history: bool = False, neutral_timing: bool = False
) -> Text:
    """The time column, greyed once the row is more than a day old.

    The text says when; the colour says whether it is still worth reacting to.
    The two disagree either side of the yesterday boundary - 00:30 last night
    is recent by breakfast and 23:00 the night before is not, though both read
    as yesterday - so recency is measured in hours rather than taken from the
    same calendar test the text uses.
    """
    field = "time" if time.time() - ts < _DAY_SECONDS else "time_old"
    return styled_cell(
        format_timestamp(ts), is_unread, field, history=history, neutral_timing=neutral_timing
    )


def _decorated_name(n: db.Notification, emojis: abc.Mapping[str, str]) -> str:
    """The session's name, after its emoji when it has one."""
    decoration = emojis.get(n.channel, "")
    return f"{decoration} {n.name or ''}".rstrip() if decoration else n.name or ""


def name_cell(
    n: db.Notification,
    emojis: abc.Mapping[str, str],
    wordybin: str,
    is_unread: bool,
    pr_number: pr_numbers.PR | None = None,
) -> Text:
    """The decorated name with its PR number and optional grey brief name."""
    name = styled_cell(_decorated_name(n, emojis), is_unread, "name")
    if pr_number:
        offset = len(emojis[n.channel]) + 1 if emojis.get(n.channel) else 0
        number = styled_cell(f"#{pr_number.number} ", is_unread, "name")
        number.stylize("bold")
        if pr_number.url:
            number.stylize(Style(link=pr_number.url), 0, len(number) - 1)
        name = name[:offset] + number + name[offset:]
    if not wordybin:
        return name

    suffix = styled_cell(f" · {wordybin}", False, "backend")
    suffix.stylize(Style(meta={"lemonaid_wordybin": True}))
    return name + suffix


def format_wake_time(until: float, now: float | None = None) -> str:
    """Render a wake time as a short human label (e.g. '14:30', 'Fri 09:00')."""
    now = now if now is not None else time.time()
    wake = datetime.fromtimestamp(until)
    if wake.date() == datetime.fromtimestamp(now).date():
        return wake.strftime("%H:%M")

    return wake.strftime("%a %H:%M")
