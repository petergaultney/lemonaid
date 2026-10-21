"""Which lemons' names are in use, so a new lemon never signs the way a current one does.

A Lemon-ID holds its name half, and so do its aliases, while its brief is active:
a session attached to it is not archived, or it saw activity within the idle
window. Nothing is stored; archiving a session never frees a name until the
window passes, and un-archiving one holds the name again at once.
"""

import sqlite3
import time
from collections import abc, defaultdict
from pathlib import Path

from ..config import load_config
from . import names

_DAY = 24 * 60 * 60
_BRIEFS = """
SELECT i.path, i.lemon_id,
  MAX(n.status IS NOT NULL AND n.status != 'archived') AS live,
  MAX(MAX(n.created_at, COALESCE(n.read_at, 0), COALESCE(n.turn_at, 0))) AS last
FROM lemon_identities i
LEFT JOIN session_briefs b ON b.path = i.path
LEFT JOIN notifications n ON n.channel = b.channel
GROUP BY i.path
"""


def _modified(path: str) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def _active_ids(conn: sqlite3.Connection, since: float, excluding: str) -> set[str]:
    return {
        row["lemon_id"]
        for row in conn.execute(_BRIEFS)
        if row["path"] != excluding
        and (row["live"] or (row["last"] or 0.0) >= since or _modified(row["path"]) >= since)
    }


def window_start(idle_days: int, now: float) -> float:
    """The start of the idle window; with *idle_days* 0, the start of time."""
    return now - idle_days * _DAY if idle_days > 0 else 0.0


def holders(
    conn: sqlite3.Connection, since: float, excluding: Path | None = None
) -> dict[str, set[str]]:
    """Each held name, lowercased, and the active Lemon-IDs holding it, directly or by alias.

    *since* is the start of the idle window; 0 holds every name ever registered.
    The brief at *excluding* holds nothing, so a lemon being renamed can be checked
    against everyone else.
    """
    active = _active_ids(conn, since, str(excluding.resolve()) if excluding else "")
    aliases = conn.execute("SELECT old_id, lemon_id FROM lemon_aliases").fetchall()
    held: dict[str, set[str]] = defaultdict(set)
    for owner, lemon_id in [
        *((i, i) for i in active),
        *((row["lemon_id"], row["old_id"]) for row in aliases if row["lemon_id"] in active),
    ]:
        if name := names.split_id(lemon_id)[0]:
            held[name.lower()].add(owner)

    return dict(held)


def shared(held: abc.Mapping[str, abc.Set[str]]) -> dict[str, set[str]]:
    """The names more than one active lemon holds."""
    return {name: ids for name, ids in held.items() if len(ids) > 1}


def held(conn: sqlite3.Connection, excluding: Path | None = None) -> set[str]:
    """The names, lowercased, a new lemon can't take now, under `[brief] name_idle_days`."""
    since = window_start(load_config().brief.name_idle_days, time.time())
    return set(holders(conn, since, excluding))


def holding(conn: sqlite3.Connection, name: str) -> set[str]:
    """The active Lemon-IDs that hold *name* now, directly or by alias."""
    since = window_start(load_config().brief.name_idle_days, time.time())
    return holders(conn, since).get(name.lower(), set())


def sharing(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """The other active Lemon-IDs that hold *lemon_id*'s name."""
    name = names.split_id(lemon_id)[0]
    if not name:
        return []

    return sorted(holding(conn, name) - {lemon_id})


def warning(lemon_id: str, others: abc.Sequence[str]) -> str:
    """What to tell *lemon_id* when *others* hold its name too, or "" when none do."""
    if not others:
        return ""

    name = names.split_id(lemon_id)[0]
    return (
        f"{name} is also the name of {', '.join(others)}, so replies signed {name} are"
        f" ambiguous. `lemonaid brief id --self --reroll` gives {lemon_id} a new name."
    )
