"""What a migration from `~/.brief-lemons/` would move, and what stops it."""

import dataclasses
import fcntl
import hashlib
import json
import os
import sqlite3
import stat
from collections import abc
from pathlib import Path

from ..messages import waiter
from . import layout

# Tables whose `path` column names a brief file.
PATH_TABLES = ("session_briefs", "pending_briefs", "lemon_identities")


@dataclasses.dataclass(frozen=True)
class Entry:
    relative: str  # under the old home, "/"-separated
    directory: bool
    size: int
    sha256: str  # "" for a directory


@dataclasses.dataclass(frozen=True)
class Plan:
    old: Path
    new_briefs: Path
    new_inbox: Path
    entries: list[Entry]
    db_rows: dict[str, int]  # table -> rows whose path is under the old home
    blockers: list[str]
    armed: list[str]  # Lemon-IDs whose inbox waiter holds its lock


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def destination(old: Path, relative: str) -> Path:
    """Where *relative* goes: `inbox/...` to the new inbox, everything else to `brief/`."""
    first, _, rest = relative.partition("/")
    if first == "inbox":
        return layout.lemons_dir() / "inbox" / rest if rest else layout.lemons_dir() / "inbox"

    return layout.lemons_dir() / "brief" / relative


def _walk(old: Path) -> abc.Iterator[tuple[Entry | None, str]]:
    """Each entry under *old*, or (None, why) for one that can't be moved safely."""
    for root, dirs, files in os.walk(old):
        dirs.sort()
        for name in [*dirs, *sorted(files)]:
            path = Path(root) / name
            relative = path.relative_to(old).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                yield None, f"{path} is a symlink"
            elif stat.S_ISDIR(mode):
                yield Entry(relative, True, 0, ""), ""
            elif stat.S_ISREG(mode):
                yield Entry(relative, False, path.stat().st_size, sha256(path)), ""
            else:
                yield None, f"{path} is not a regular file or directory"


def _held(lock: Path) -> bool:
    try:
        f = lock.open()
    except FileNotFoundError:
        return False

    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True

        return False


def armed_waiters(inbox_root: Path) -> list[str]:
    if not inbox_root.is_dir():
        return []

    return sorted(p.name for p in inbox_root.iterdir() if p.is_dir() and waiter.is_armed(p))


def db_paths(conn: sqlite3.Connection, old: Path) -> abc.Iterator[tuple[str, str]]:
    """(table, path) for each row naming a file under *old*."""
    prefix = f"{old}/"
    for table in PATH_TABLES:
        for (path,) in conn.execute(f"SELECT path FROM {table}"):
            if path.startswith(prefix):
                yield table, path


def unsafe_destinations(targets: abc.Iterable[Path]) -> list[str]:
    """Why a copy to *targets* could land outside `~/.lemons/`: a symlink or a
    non-directory at the home or any directory between it and a target."""
    home = layout.lemons_dir()
    checked: set[Path] = set()
    problems: list[str] = []
    for target in targets:
        between = reversed(target.relative_to(home).parents[:-1])
        for path in [home, *(home / directory for directory in between)]:
            if path in checked:
                continue

            checked.add(path)
            if path.is_symlink():
                problems.append(f"{path} is a symlink")
            elif path.exists() and not path.is_dir():
                problems.append(f"{path} is not a directory")

    return problems


def plan(conn: sqlite3.Connection) -> Plan:
    if layout.legacy_dir().is_symlink():
        empty = Plan(
            layout.legacy_dir(),
            layout.lemons_dir() / "brief",
            layout.lemons_dir() / "inbox",
            [],
            {},
            [],
            [],
        )
        return dataclasses.replace(empty, blockers=[f"{layout.legacy_dir()} is a symlink"])

    old = layout.legacy_dir().resolve()
    walked = list(_walk(old)) if old.is_dir() else []
    entries = [entry for entry, _ in walked if entry]
    blockers = [why for entry, why in walked if not entry]
    blockers += unsafe_destinations(
        [destination(old, e.relative) for e in entries]
        + [
            layout.lemons_dir() / "brief" / "x",
            layout.lemons_dir() / "inbox" / "x",
            layout.lemons_dir() / "migrations" / "x",
        ]
    )
    if (layout.lemons_dir() / layout.CUTOVER).exists():
        blockers.append(f"{layout.lemons_dir() / layout.CUTOVER} exists: already migrated")

    if not old.is_dir():
        blockers.append(f"No old home at {old}")

    blockers += [
        f"{target} already exists"
        for entry in entries
        if not entry.directory and (target := destination(old, entry.relative)).exists()
    ]
    rows: dict[str, int] = {}
    files = {entry.relative for entry in entries if not entry.directory}
    for table, path in db_paths(conn, old):
        rows[table] = rows.get(table, 0) + 1
        if Path(path).relative_to(old).as_posix() not in files:
            blockers.append(f"{table} names {path}, which does not exist")

    armed = armed_waiters(old / "inbox")
    blockers += [f"An inbox waiter is armed for {lemon_id}" for lemon_id in armed]
    if _held(old / "inbox" / ".delivery.lock"):
        blockers.append("The Codex delivery service is running")

    return Plan(
        old,
        layout.lemons_dir() / "brief",
        layout.lemons_dir() / "inbox",
        entries,
        rows,
        blockers,
        armed,
    )


def to_json(found: Plan) -> str:
    return json.dumps(
        {
            "old": str(found.old),
            "new_briefs": str(found.new_briefs),
            "new_inbox": str(found.new_inbox),
            "files": sum(not e.directory for e in found.entries),
            "directories": sum(e.directory for e in found.entries),
            "bytes": sum(e.size for e in found.entries),
            "db_rows": found.db_rows,
            "armed_waiters": found.armed,
            "blockers": found.blockers,
        }
    )
