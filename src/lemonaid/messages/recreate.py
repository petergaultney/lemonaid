"""Put back what a tossed lemon ran in, so `lemon resume --recreate` can resume it there.

A toss archives the lemon's brief, closes its tmux session, and may release its
directory. Each comes back the way it was made: the brief from the attic, the
directory through its root's hooks, and the session (`autoresume_tmux.recreate`)
under its recorded name on its recorded server. Nothing is guessed: a directory whose place the places log
doesn't name is refused, never replaced by a parent directory.
"""

import sqlite3
import typing as ty
from collections import abc
from pathlib import Path

from ..brief import archive, archived_channel, attached, identity, lemon
from ..config import Config
from ..inbox import db
from ..places import audit, lifecycle


class Place(ty.NamedTuple):
    key: str
    directory: Path


def archived_id(conn: sqlite3.Connection, target: str) -> str:
    """The Lemon-ID *target* names if its brief is in the attic, else "".

    *target* is the Lemon-ID or either half of it.
    """
    if identity.valid(target) and (path := lemon.brief_of(conn, target)) is not None:
        return lemon.current(conn, target) if archive.is_archived(path) else ""

    matches = [
        row["lemon_id"]
        for row in conn.execute("SELECT lemon_id, path FROM lemon_identities")
        if target in row["lemon_id"].split(".") and archive.is_archived(Path(row["path"]))
    ]
    return matches[0] if len(matches) == 1 else ""


def _holder(conn: sqlite3.Connection, channel: str) -> str:
    row = conn.execute("SELECT path FROM session_briefs WHERE channel = ?", (channel,)).fetchone()
    return row["path"] if row else ""


def _taken(lemon_id: str, channel: str, holder: str) -> str:
    return (
        f"{lemon_id}'s session {channel} has another brief attached now ({Path(holder).name}), "
        "so lemonaid won't take it over"
    )


def brief(conn: sqlite3.Connection, lemon_id: str) -> Path:
    """Bring *lemon_id*'s brief back from the attic, attached to the session it last had.

    Raises LookupError when no session was recorded for it, and ValueError when it can't be
    revived or its session holds another brief. A brief attached there between the revive and
    the attach is kept, and this brief stays revived but unattached.
    """
    channel = archived_channel.of(conn, lemon_id)
    if not channel or db.get_by_channel(conn, channel, unread_only=False) is None:
        raise LookupError(
            f"{lemon_id}'s brief is archived, and lemonaid didn't record which session it "
            f"was attached to. Run `lemonaid brief revive {lemon_id}`, then attach it to the "
            "lemon's session and resume that"
        )

    if holder := _holder(conn, channel):
        raise ValueError(_taken(lemon_id, channel, holder))

    path = archive.revive(conn, lemon_id)
    conn.execute("BEGIN IMMEDIATE")
    if holder := _holder(conn, channel):
        conn.rollback()
        raise ValueError(f"{_taken(lemon_id, channel, holder)}; its brief is back at {path}")

    attached.attach(conn, channel, path)  # commits
    return path


def place_of(cwd: Path, events: abc.Iterable[dict]) -> Place | None:
    """The place holding *cwd* that the places log last opened or tossed, innermost first."""
    found = [
        Place(event["key"], Path(event["dir"]))
        for event in events
        if event.get("action") in ("open", "toss")
        and event.get("key")
        and event.get("dir")
        and cwd.is_relative_to(Path(event["dir"]))
    ]
    return max(reversed(found), key=lambda place: len(place.directory.parts), default=None)


def directory(cwd: str, config: Config) -> tuple[str, str]:
    """Recreate *cwd* through its place's hooks if it is gone: (what was done, why not)."""
    if not cwd:
        return "", "no working directory is recorded for it"

    if Path(cwd).is_dir():
        return "", ""

    place = place_of(Path(cwd), audit.entries(0))
    root = config.places.root_for(place.directory) if place else None
    if place is None or root is None:
        return "", (
            f"its directory {cwd} is gone, and lemonaid can't tell which place it was: no place "
            "under a configured root holds it in the places log. Recreate the directory "
            "(`lemonaid place acquire <key>`), then resume it again"
        )

    made, why = lifecycle.acquire_key(place.key, root)
    if made is None:
        return "", f"its directory {cwd} is gone and could not be recreated: {why}"

    if made.resolve() != place.directory.resolve():
        return "", (
            f"its directory {cwd} is gone, and {root.path}'s hooks put {place.key!r} at "
            f"{made}, not {place.directory}"
        )

    if not Path(cwd).is_dir():
        return "", f"{place.key!r} is back at {made}, but {cwd} is not in it"

    return f"recreated {place.key!r} at {made}", ""
