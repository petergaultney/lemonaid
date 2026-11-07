"""An append-only record of who opened, tossed, or was refused a toss of a place.

One JSON object per line in `places.log` under the state directory; see `audit.journal`
for rotation and `audit.actor` for how the caller is named.
"""

from collections import abc

from ..audit import actor, events, journal
from ..log import get_logger

_log = get_logger("places.audit")


def record(
    action: str,
    outcome: str,
    key: str = "",
    directory: str = "",
    session: str = "",
    flags: abc.Sequence[str] = (),
    reason: str = "",
) -> None:
    """Append one event; a failure to write is logged and never stops the action itself."""
    try:
        caller = actor.caller()
    except (OSError, ValueError, UnicodeError) as e:
        _log.warning("could not name the caller for the place audit log: %s", e)
        caller = {"who": "unknown", "via": ""}
    journal.append(
        events.PLACES,
        {
            "at": events.now(),
            "action": action,
            "outcome": outcome,
            "key": key,
            "dir": directory,
            "session": session,
            "flags": list(flags),
            "reason": reason,
            **caller,
        },
    )


def entries(limit: int, key: str = "") -> list[dict]:
    """The last *limit* events, oldest first, optionally only those naming *key* (or session *key*)."""
    found = [
        e for e in journal.read(events.PLACES) if not key or key in (e.get("key"), e.get("session"))
    ]

    return found[-limit:] if limit > 0 else found
