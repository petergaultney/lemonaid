"""Whether each briefed lemon in the inbox would read a message now: its card's `deaf` or `dead` mark.

The facts are the ones `lemonaid tell` checks (`messages.recipient`), gathered
for every row at once and kept for a few seconds, since the inbox redraws
several times a second.

A Claude lemon is deaf for a moment each time its inbox waiter delivers a
message and before it rearms one, so `deaf` waits until it has lasted.
"""

import subprocess
from collections import abc

from ..messages import recipient, store, waiter
from . import db

DEAF = "deaf"
DEAD = "dead"

_TTL_SECONDS = 10.0
DEAF_AFTER_SECONDS = 15.0
_MARKS = {recipient.DEAF: DEAF, recipient.DEAD: DEAD}


def _harness_ttys() -> frozenset[str] | None:
    """Each terminal a harness runs on, as `ps` names it, or None if `ps` could not say."""
    try:
        result = subprocess.run(["ps", "-A", "-o", "tty=,comm="], capture_output=True, text=True)
    except OSError:
        return None

    if result.returncode != 0:
        return None

    listed = (line.split(maxsplit=1) for line in result.stdout.splitlines())
    return frozenset(
        parts[0] for parts in listed if len(parts) == 2 and recipient.is_harness(parts[1].strip())
    )


def _alive(row: db.Notification, ttys: frozenset[str] | None, listed_at: float) -> bool | None:
    """None when unknowable, including for a row reported since the listing was taken."""
    tty = str(row.metadata.get("tty") or "").removeprefix("/dev/")
    if not tty or ttys is None or max(row.created_at, row.turn_at or 0.0) >= listed_at:
        return None

    return tty in ttys


def _armed(lemon_id: str) -> bool | None:
    """None when the ID names no inbox lemonaid can check."""
    try:
        return waiter.is_armed(store.inbox_for_id(lemon_id))
    except ValueError:
        return None


class Probe:
    """Caches the `ps` listing the marks come from for `_TTL_SECONDS`; waiter locks are read every time.

    A lemon is marked `deaf` once it has been deaf for *deaf_after* seconds of calls.
    """

    def __init__(self, deaf_after: float = 0.0) -> None:
        self._at = float("-inf")
        self._ttys: frozenset[str] | None = None
        self._deaf_after = deaf_after
        self._deaf_since: dict[str, float] = {}

    def marks(
        self, rows: abc.Iterable[db.Notification], lemon_ids: abc.Mapping[str, str], now: float
    ) -> dict[str, str]:
        """`deaf` or `dead` for each row of *rows* in *lemon_ids* that is one, by channel."""
        if now - self._at >= _TTL_SECONDS:
            self._at, self._ttys = now, _harness_ttys()

        found = {}
        deaf_since = {}
        for row in rows:
            if (lemon_id := lemon_ids.get(row.channel)) is None:
                continue
            if (armed := _armed(lemon_id)) is None:
                continue
            state = recipient.classify(
                row.channel, row, _alive(row, self._ttys, self._at), armed, now
            )
            if state.state == recipient.DEAF:
                deaf_since[row.channel] = self._deaf_since.get(row.channel, now)
                if now - deaf_since[row.channel] < self._deaf_after:
                    continue
            if mark := _MARKS.get(state.state):
                found[row.channel] = mark
        self._deaf_since = deaf_since
        return found
