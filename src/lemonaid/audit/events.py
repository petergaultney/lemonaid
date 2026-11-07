"""Who moved, removed or rewrote state that a person or another lemon owns, and why.

Each event names its `action`, the `thing` acted on (a brief, a Lemon-ID, an inbox
channel), `why`, any action-specific fields, the command line, and the actor with its
evidence (see `actor`). Place opens and tosses keep their own log, `places.log`;
`entries` reads both.
"""

import datetime
import shlex
import sys

from . import actor, journal

ACTIONS = "actions.log"
PLACES = "places.log"
_ARGV_CHARS = 300
_SEARCHED = ("thing", "key", "session", "dir", "from", "to", "channel")


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def argv() -> str:
    return shlex.join(sys.argv[1:])[:_ARGV_CHARS]


def record(action: str, thing: str, why: str = "", by: str = "", **detail: str) -> None:
    """Append one event; *by* names a lemonaid job that acts on its own account.

    Never raises: an action is not stopped or failed by its audit record.
    """
    try:
        entry = {
            "at": now(),
            "action": action,
            "thing": thing,
            "why": why,
            **detail,
            "argv": argv(),
            **actor.caller(by),
        }
    except (OSError, ValueError, UnicodeError) as e:
        entry = {"at": now(), "action": action, "thing": thing, "why": why, "actor_error": str(e)}
    journal.append(ACTIONS, entry)


def _normal(entry: dict) -> dict:
    """A place event with the `thing` and `why` that action events carry."""
    return {
        **entry,
        "thing": entry.get("thing") or entry.get("key") or entry.get("session") or "",
        "why": entry.get("why") or entry.get("reason") or "",
    }


def _when(entry: dict) -> float:
    try:
        return datetime.datetime.fromisoformat(str(entry.get("at", ""))).timestamp()
    except ValueError:
        return 0.0


def _matches(entry: dict, by: str, thing: str) -> bool:
    return (not by or by.lower() in str(entry.get("who", "")).lower()) and (
        not thing or any(thing.lower() in str(entry.get(k, "")).lower() for k in _SEARCHED)
    )


def entries(limit: int, by: str = "", thing: str = "") -> list[dict]:
    """The last *limit* events from both logs, oldest first (0 for all).

    *by* and *thing* match case-insensitive substrings: of the actor, and of the thing
    acted on, its place key, tmux session, directory, source, destination or channel.
    """
    found = sorted(
        (
            e
            for e in map(_normal, [*journal.read(PLACES), *journal.read(ACTIONS)])
            if _matches(e, by, thing)
        ),
        key=_when,
    )
    return found[-limit:] if limit > 0 else found
