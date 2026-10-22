"""Whether each briefed lemon in the inbox would read a message now: its card's `deaf` or `dead` mark.

The facts are the ones `lemonaid tell` checks (`messages.recipient`), gathered
for every row at once and kept for a few seconds, since the inbox redraws
several times a second.

A Claude lemon is deaf for a moment each time its inbox waiter delivers a
message and before it rearms one, so `deaf` waits until it has lasted.
"""

import threading
import typing as ty
from collections import abc

from .. import handlers
from ..lemon_watchers import tty_processes
from ..log import get_logger
from ..messages import recipient, store, waiter
from . import db

_log = get_logger("inbox.presence")

DEAF = "deaf"
DEAD = "dead"

_TTL_SECONDS = 10.0
DEAF_AFTER_SECONDS = 15.0
_MARKS = {recipient.DEAF: DEAF, recipient.DEAD: DEAD}


def _harness_ttys() -> frozenset[str] | None:
    """Each terminal a harness runs on, as `ps` names it, or None if `ps` could not say."""
    listed = tty_processes.listing("comm")
    if listed is None:
        return None

    return frozenset(tty for tty, command in listed if recipient.is_harness(command))


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


class _Listing(ty.NamedTuple):
    at: float
    ttys: frozenset[str] | None
    confirmed: dict[str, tuple[db.Notification, bool | None]]


def _confirming(row: db.Notification, listing: _Listing) -> bool:
    return (
        row.switch_source in handlers.PER_SESSION_SOURCES
        or _alive(row, listing.ttys, listing.at) is False
    )


class Probe:
    """Caches the `ps` listing the marks come from for `_TTL_SECONDS`; waiter locks are read every time.

    A lemon is marked `deaf` once it has been deaf for *deaf_after* seconds of calls.
    Batch misses are confirmed with the same recipient probe as `lemon doctor`.

    With *background*, the listing and its confirmations are taken on a thread
    and a caller sees the previous ones until it finishes: `ps -A` can take a
    second, too long to block an event loop for.
    """

    def __init__(self, deaf_after: float = 0.0, background: bool = False) -> None:
        self._listing = _Listing(float("-inf"), None, {})
        self._listing_pending = False
        self._background = background
        self._deaf_after = deaf_after
        self._deaf_since: dict[str, float] = {}

    def _list(self, rows: abc.Sequence[db.Notification], now: float) -> None:
        try:
            listing = _Listing(now, _harness_ttys(), {})
            for row in rows:
                if _confirming(row, listing):
                    listing.confirmed[row.channel] = (row, recipient.harness_alive(row))
            self._listing = listing
        except Exception:
            _log.exception("could not list harness terminals")
        finally:
            self._listing_pending = False

    def _relist(self, rows: abc.Sequence[db.Notification], now: float) -> None:
        if not self._background:
            self._listing = _Listing(now, _harness_ttys(), {})
            return

        if not self._listing_pending:
            self._listing_pending = True
            threading.Thread(
                target=self._list, args=(rows, now), daemon=True, name="presence"
            ).start()

    def _alive(self, row: db.Notification) -> bool | None:
        listing = self._listing
        if row.switch_source not in handlers.PER_SESSION_SOURCES:
            alive = _alive(row, listing.ttys, listing.at)
            if alive is not False:
                return alive

        confirmed = listing.confirmed.get(row.channel)
        if confirmed is not None and confirmed[0] == row:
            return confirmed[1]

        if self._background:
            return None

        listing.confirmed[row.channel] = (row, recipient.harness_alive(row))
        return listing.confirmed[row.channel][1]

    def marks(
        self, rows: abc.Iterable[db.Notification], lemon_ids: abc.Mapping[str, str], now: float
    ) -> dict[str, str]:
        """`deaf` or `dead` for each row of *rows* in *lemon_ids* that is one, by channel."""
        candidates = [
            (row, armed)
            for row in rows
            if (lemon_id := lemon_ids.get(row.channel)) is not None
            and (armed := _armed(lemon_id)) is not None
        ]
        if now - self._listing.at >= _TTL_SECONDS:
            self._relist([row for row, _ in candidates], now)

        found = {}
        deaf_since = {}
        for row, armed in candidates:
            state = recipient.classify(row.channel, row, self._alive(row), armed, now)
            if state.state == recipient.DEAF:
                deaf_since[row.channel] = self._deaf_since.get(row.channel, now)
                if now - deaf_since[row.channel] < self._deaf_after:
                    continue
            if mark := _MARKS.get(state.state):
                found[row.channel] = mark
        self._deaf_since = deaf_since
        return found
