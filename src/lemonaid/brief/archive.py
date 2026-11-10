"""Moving briefs nobody uses out of the briefs directory, and back.

An archived brief goes to the attic, in a folder for the month it was last used, with its
mailbox beside it. It keeps its Lemon-ID: `lemon_identities` points at its new place, so a
lookup by ID still finds it, while nothing that scans attachments sees it again.
"""

import contextlib
import datetime
import itertools
import os
import sqlite3
import time
import typing as ty
from collections import abc
from pathlib import Path

from .. import home
from ..audit import events
from ..log import get_logger
from ..messages import store as messages
from ..tasks.briefs import completion, liveness
from . import active_names, archived_channel, frontmatter, identity, status, store

_log = get_logger("brief.archive")

_DAY = 24 * 60 * 60
_WAITING = frozenset({"blocked", "alert", "merge", "approve", "review", "running"})


class Idle(ty.NamedTuple):
    path: Path
    lemon_id: str  # "" when the brief has none
    last: float  # when it was last in use


def attic_dir() -> Path:
    if os.environ.get("LEMONAID_BRIEFS_DIR"):
        return store.briefs_dir() / "attic"

    return home.layout.attic_dir()


def is_archived(path: Path) -> bool:
    return path.resolve().is_relative_to(attic_dir().resolve())


def _mailbox_touched(lemon_id: str) -> float:
    if not lemon_id:
        return 0.0

    mailbox = messages.mailbox_root() / lemon_id
    return max(active_names.modified(mailbox), active_names.modified(mailbox / "done"))


def _held(conn: sqlite3.Connection, path: Path) -> float:
    """When *path* was last attached or requested; inf while a handoff of it is under way."""
    if conn.execute(
        "SELECT 1 FROM brief_handoffs WHERE path = ? AND phase NOT IN ('complete', 'failed')",
        (str(path),),
    ).fetchone():
        return float("inf")

    row = conn.execute(
        "SELECT MAX(at) FROM (SELECT attached_at AS at FROM session_briefs WHERE path = ?"
        " UNION ALL SELECT requested_at FROM pending_briefs WHERE path = ?)",
        (str(path), str(path)),
    ).fetchone()
    return row[0] or 0.0


def _live_elsewhere(conn: sqlite3.Connection, path: Path, closing: abc.Set[str]) -> bool:
    """Whether a session other than those in *closing* holds *path* and is not archived."""
    return any(
        row["channel"] not in closing
        for row in conn.execute(
            "SELECT b.channel FROM session_briefs b JOIN notifications n ON n.channel = b.channel"
            " WHERE b.path = ? AND n.status != 'archived'",
            (str(path),),
        )
    )


def _created(path: Path) -> float:
    try:
        at = frontmatter.fields(path.read_text()).get("created", {}).get("at")
    except (OSError, ValueError, AttributeError):
        return 0.0

    if isinstance(at, str):
        try:
            at = datetime.datetime.fromisoformat(at)
        except ValueError:
            return 0.0
    return at.timestamp() if isinstance(at, datetime.datetime) else 0.0


def _status_changed(conn: sqlite3.Connection, path: Path) -> float:
    row = conn.execute("SELECT since FROM brief_status_since WHERE path = ?", (str(path),))
    found = row.fetchone()
    return found["since"] if found else 0.0


def _last(conn: sqlite3.Connection, path: Path, use: active_names.Usage | None) -> float:
    """When *path* was last in use; inf while a session attached to it is live.

    In use: it was created, its Status changed, a session attached to it was active, it
    was attached or requested, or its mailbox got a message. The file's mtime doesn't
    count: lemonaid's own migrations rewrite every brief.
    """
    if use is not None and use.live:
        return float("inf")

    return max(
        use.last if use else 0.0,
        _created(path),
        _status_changed(conn, path),
        _held(conn, path),
        _mailbox_touched(use.lemon_id if use else ""),
    )


def last_used(conn: sqlite3.Connection, path: Path) -> float:
    return _last(
        conn, path, next((u for u in active_names.usage(conn) if u.path == str(path)), None)
    )


def _kept(conn: sqlite3.Connection, path: Path, lemon_id: str) -> bool:
    """Whether the sweep must leave *path*: its Status waits on someone, or its lemon runs.

    The inbox's attached-session check misses a live harness whose row was archived or
    attached under another channel, so the harness itself is probed too.
    """
    try:
        if status.split(path.read_text()).status in _WAITING:
            return True
    except OSError:
        return True

    return bool(lemon_id) and liveness.live(conn, lemon_id)


def idle(conn: sqlite3.Connection, days: float, now: float) -> list[Idle]:
    """Oldest first; never a brief whose Status waits on someone or whose lemon is live."""
    since = now - days * _DAY
    used = {Path(u.path): u for u in active_names.usage(conn)}
    found = [
        Idle(path, use.lemon_id if use else "", last)
        for path in (
            p.resolve()
            for p in store.briefs_dir().glob("*.md")
            if not p.is_symlink() and p.is_file()
        )
        for use in [used.get(path)]
        for last in [_last(conn, path, use)]
        if last < since
    ]
    return sorted((i for i in found if not _kept(conn, i.path, i.lemon_id)), key=lambda i: i.last)


def _lemon_id(conn: sqlite3.Connection, path: Path) -> str:
    row = conn.execute("SELECT lemon_id FROM lemon_identities WHERE path = ?", (str(path),))
    if found := row.fetchone():
        return found["lemon_id"]

    try:
        return identity.read(path.read_text())
    except ValueError:
        return ""


def _repoint(conn: sqlite3.Connection, old: Path, new: Path) -> None:
    """Move *old*'s rows to *new*.

    Status and Needs timing are rebuilt from the file, and a reader that had it open as it moved
    can record a row at *new*; the *old* row is the one that tracked this file, so it replaces
    that. A Lemon-ID already registered at *new* is a real conflict and raises.
    """
    if old == new:
        return

    conn.execute("UPDATE lemon_identities SET path = ? WHERE path = ?", (str(new), str(old)))
    for table in ("brief_status_since", "brief_needs_since"):
        if conn.execute(f"SELECT 1 FROM {table} WHERE path = ?", (str(old),)).fetchone():
            conn.execute(f"DELETE FROM {table} WHERE path = ?", (str(new),))
        conn.execute(f"UPDATE {table} SET path = ? WHERE path = ?", (str(new), str(old)))


def _free(folder: Path) -> Path:
    """The next numbered slot in *folder*: one per archive, so a revived lemon archived again keeps both."""
    return next(slot for n in itertools.count(1) if not (slot := folder / str(n)).exists())


def _archived_mailboxes(folder: Path) -> list[Path]:
    """The slots `_free` filled in *folder*, oldest first."""
    return sorted(
        (slot for slot in folder.glob("*") if slot.is_dir() and slot.name.isdigit()),
        key=lambda slot: int(slot.name),
    )


def _merge_mailbox(source: Path, dest: Path) -> None:
    """Move *source*'s messages into *dest*, keeping any already there.

    Lock files are the receivers' and are dropped when *dest* has its own. A message both
    hold stays in *source*, which is removed once empty.
    """
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
        return

    for entry in sorted(source.rglob("*")):
        moved = dest / entry.relative_to(source)
        if not entry.is_file():
            continue

        if not moved.exists():
            moved.parent.mkdir(parents=True, exist_ok=True)
            entry.rename(moved)
        elif entry.name.endswith(".lock"):
            entry.unlink()
    for folder in sorted((d for d in source.rglob("*") if d.is_dir()), reverse=True):
        with contextlib.suppress(OSError):
            folder.rmdir()
    with contextlib.suppress(OSError):
        source.rmdir()


def archive(
    conn: sqlite3.Connection,
    path: Path,
    last: float,
    closing: abc.Set[str] = frozenset(),
    *,
    why: str,
) -> Path:
    """Move *path* and its mailbox to the attic and detach it; where the brief went.

    *last* names the attic month. Sessions in *closing* are ending and don't hold it.
    *why* goes into the audit log beside who moved it.
    Raises ValueError when another session still holds it, the attic already has a brief
    of that name, or a home migration is under way.
    """
    month = attic_dir() / time.strftime("%Y-%m", time.localtime(last or time.time()))
    target = month / path.name
    if lemon_id := _lemon_id(conn, path):
        for line in completion.hand_on_archive(conn, lemon_id):
            _log.info("%s", line)
    with home.guard.operation():
        conn.execute("BEGIN IMMEDIATE")
        try:
            if _live_elsewhere(conn, path, closing):
                raise ValueError(f"{path.name} is attached to a live session")

            if target.exists():
                raise ValueError(f"{target} already exists")

            lemon_id = _lemon_id(conn, path)
            if lemon_id:
                archived_channel.remember(conn, lemon_id, str(path))
            _repoint(conn, path, target)
            conn.execute("DELETE FROM session_briefs WHERE path = ?", (str(path),))
            conn.execute("DELETE FROM pending_briefs WHERE path = ?", (str(path),))
            month.mkdir(parents=True, exist_ok=True)
            path.rename(target)
            mailbox = messages.mailbox_root() / lemon_id if lemon_id else None
            mailbox_to = ""
            if mailbox is not None and mailbox.is_dir() and not mailbox.is_symlink():
                try:
                    kept = month / home.layout.MAILBOX / lemon_id
                    kept.mkdir(parents=True, exist_ok=True)
                    mailbox_to = str(_free(kept))
                    mailbox.rename(mailbox_to)
                except OSError:
                    target.rename(path)
                    raise
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
    events.record(
        "brief-archive",
        lemon_id or path.name,
        why,
        **{"from": str(path), "to": str(target), "mailbox": mailbox_to},
    )
    return target


def _attic_brief(name: str, lemon_id: str) -> Path | None:
    """The one attic file called *name* that carries *lemon_id*; None when none or several do."""
    found = []
    for candidate in attic_dir().glob(f"*/{name}"):
        try:
            if identity.read(candidate.read_text()) == lemon_id:
                found.append(candidate)
        except (OSError, ValueError):
            continue

    return found[0] if len(found) == 1 else None


def revive(conn: sqlite3.Connection, lemon_id: str, *, why: str) -> Path:
    """Move an archived brief and its mailbox back to the briefs directory; where it went.

    It comes back unattached, and the move is audited with *why*. Raises LookupError when *lemon_id* has no archived brief and
    ValueError when the briefs directory already has one of that name or a home migration
    is under way.
    """
    row = conn.execute("SELECT path FROM lemon_identities WHERE lemon_id = ?", (lemon_id,))
    found = row.fetchone()
    recorded = Path(found["path"]) if found else None
    path = recorded
    if recorded is not None and not recorded.exists() and not is_archived(recorded):
        path = _attic_brief(recorded.name, lemon_id)  # the record never followed the file
    if path is None or not is_archived(path):
        raise LookupError(f"{lemon_id} has no archived brief")

    target = store.briefs_dir() / path.name
    with home.guard.operation():
        conn.execute("BEGIN IMMEDIATE")
        try:
            if target.exists():
                raise ValueError(f"{target} already exists")

            _repoint(conn, recorded, target)
            path.rename(target)
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
        for name in (home.layout.OLD_MAILBOX, home.layout.MAILBOX):
            kept = path.parent / name / lemon_id
            for archived in _archived_mailboxes(kept):
                _merge_mailbox(archived, messages.mailbox_root() / lemon_id)
            with contextlib.suppress(OSError):
                kept.rmdir()
    events.record("brief-revive", lemon_id, why, **{"from": str(path), "to": str(target)})
    return target
