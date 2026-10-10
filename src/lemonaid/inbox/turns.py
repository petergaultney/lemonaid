"""Whether a lemon is mid-turn, and the brief status it shows while it is.

A brief without a status shows `active` while its lemon is mid-turn. With
`mid_turn_working`, so does a brief whose lemon rewrites its `Status:` late in
a turn and still says `blocked` while it works on your answer; the brief's own
status applies again once the turn ends. Only the drawing changes: the brief's
own status still places it in the list. `running` stays: it means minding a
process across turns.
"""

from collections import abc
from pathlib import Path

from . import db

# A turn whose transcript has been silent this long counts as over. A session
# killed mid-turn never writes the entry that ends it.
STALE_SECONDS = 20 * 60
_KEPT = frozenset({"running"})


def mid_turn(n: db.Notification, now: float) -> bool:
    """Whether *n*'s lemon is mid-turn.

    An unread row is not: its lemon has stopped to ask for something, such as a
    permission prompt, even with the turn still open.
    """
    return n.turn_at is not None and not n.is_unread and now - n.turn_at < STALE_SECONDS


def shown(status: str) -> str:
    """The status a mid-turn lemon whose brief says *status* shows."""
    return status if status in _KEPT else "active"


def briefs(
    rows: abc.Iterable[db.Notification], attached: abc.Mapping[str, Path], now: float
) -> frozenset[Path]:
    """The briefs attached to the lemons of *rows* that are mid-turn."""
    return frozenset(
        attached[n.channel] for n in rows if n.channel in attached and mid_turn(n, now)
    )
