"""Bring files written to `~/.brief-lemons/` after cutover into the active home.

Until this runs, brief and message commands refuse (`layout.stray`). Each late
file is published into the new home at the path the migration would have
given it, never over a different file; the old root is removed only once it
is empty. A file that collides with different content is left in place and the
refusal names it, since choosing between two versions of a brief is a person's
call.
"""

import os
import shutil
from pathlib import Path

from ..inbox import db
from . import guard, inventory, layout
from .migrate import Outcome


def _problems(old: Path) -> list[str]:
    if old.is_symlink():
        return [f"{old} is a symlink"]

    problems: list[str] = []
    for path in sorted(old.rglob("*")):
        if path.is_symlink():
            problems.append(f"{path} is a symlink")
            continue

        if path.is_dir() or not path.is_file():
            if not path.is_dir():
                problems.append(f"{path} is not a regular file or directory")
            continue

        target = inventory.destination(old, path.relative_to(old).as_posix())
        if target.exists() and inventory.sha256(target) != inventory.sha256(path):
            problems.append(f"{path} differs from {target}; merge them by hand")

    return problems + inventory.unsafe_destinations(
        inventory.destination(old, p.relative_to(old).as_posix()) for p in old.rglob("*")
    )


def _bring_in(old: Path) -> list[Path]:
    """Move each late file into the new home; returns the files published."""
    moved: list[Path] = []
    for path in sorted(p for p in old.rglob("*") if p.is_file()):
        target = inventory.destination(old, path.relative_to(old).as_posix())
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, target)  # never over an existing file
            shutil.copystat(path, target)
            moved.append(target)
        path.unlink()
    for directory in sorted((p for p in old.rglob("*") if p.is_dir()), reverse=True):
        directory.rmdir()
    old.rmdir()
    return moved


def _repoint(old: Path) -> int:
    """Point DB rows an older lemonaid wrote under *old* at the files' new paths."""
    changed = 0
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table, path in list(inventory.db_paths(conn, old)):
                target = inventory.destination(old, Path(path).relative_to(old).as_posix())
                changed += conn.execute(
                    f"UPDATE {table} SET path = ? WHERE path = ?", (str(target), path)
                ).rowcount
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    return changed


RECONCILING = "reconcile"


def reconciling(marker: Path) -> Path | None:
    """The old root a paused reconciliation was moving, or None if *marker* is another pause."""
    kind, _, old = marker.read_text().strip().partition(" ")
    return Path(old) if kind == RECONCILING and old else None


def _unfinished(old: Path) -> str:
    if old.exists() or old.is_symlink():
        return f"{old} still exists"

    with db.connect() as conn:
        stale = list(inventory.db_paths(conn, old))
    return f"{stale[0][0]} still names {stale[0][1]}" if stale else ""


def run() -> Outcome:
    """Bring late files in. A stopped run is resumed by running it again.

    The DB is repointed before any file moves, and both steps can be repeated,
    so a rerun after a stop at any point finishes the job; the pause is lifted
    only once no file or row is left in the old home.
    """
    legacy = layout.legacy_dir()
    if legacy.is_symlink():
        return Outcome(False, False, [f"Refused; nothing changed: {legacy} is a symlink"])

    expected = legacy.parent.resolve() / legacy.name  # the leaf itself is never followed
    marker = layout.lemons_dir() / layout.MIGRATING
    resuming = marker.exists()
    if resuming:
        old = reconciling(marker)
        if old is None:
            return Outcome(False, False, ["A migration is in progress; finish or abort it first"])

        if old != expected:
            return Outcome(False, True, [f"The paused reconcile names {old}, not {expected}"])
    elif not layout.stray():
        return Outcome(False, False, ["Nothing to reconcile"])
    else:
        old = expected
        with marker.open("x") as f:
            f.write(f"{RECONCILING} {old}\n")

    guard.drain()
    if (old.exists() or old.is_symlink()) and (problems := _problems(old)):
        if not resuming:
            marker.unlink()
            return Outcome(False, False, ["Refused; nothing changed:", *problems])

        return Outcome(False, True, ["Refused; still paused until these are resolved:", *problems])

    repointed = _repoint(old)
    moved = _bring_in(old) if old.exists() else []
    if error := _unfinished(old):
        return Outcome(False, True, [f"Still paused: {error}; run --reconcile again"])

    marker.unlink()
    return Outcome(
        True,
        False,
        [
            f"Brought {len(moved)} late file(s) into {layout.lemons_dir()}; "
            f"{repointed} DB path(s) repointed"
        ],
    )
