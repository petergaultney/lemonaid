"""Return to `~/.brief-lemons/` after a migration, only when nothing would be lost.

The new home must hold exactly what the migration copied: a brief edited or
created, or a message sent or read since, is work the old home doesn't have,
and the rollback refuses rather than choose between them.
"""

import os
from pathlib import Path

from ..inbox import db
from . import guard, inventory, journal, layout
from .migrate import Outcome


def _unchanged(record: journal.Journal) -> str:
    """Why the new home differs from what was copied into it, or ""."""
    expected = {inventory.destination(record.old, e.relative): e for e in record.entries}
    for root in (layout.lemons_dir() / "brief", layout.lemons_dir() / "inbox"):
        for path in root.rglob("*") if root.is_dir() else ():
            entry = expected.get(path)
            if entry is None:
                return f"{path} was added after the migration"

            if (
                not entry.directory
                and not path.name.endswith(".lock")
                and inventory.sha256(path) != entry.sha256
            ):
                return f"{path} changed after the migration"

    missing = [p for p, e in expected.items() if not e.directory and not p.exists()]
    return f"{missing[0]} was removed after the migration" if missing else ""


def _refusal(record: journal.Journal) -> str:
    if record.old.exists() or record.old.is_symlink():
        return f"{record.old} exists again"

    if not record.backup.is_dir():
        return f"No backup at {record.backup}"

    if unsafe := inventory.unsafe_destinations(
        inventory.destination(record.old, e.relative) for e in record.entries
    ):
        return unsafe[0]

    if armed := inventory.armed_waiters(layout.lemons_dir() / "inbox"):
        return f"An inbox waiter is armed for {', '.join(armed)}"

    return _unchanged(record)


def run() -> Outcome:
    cutover = layout.lemons_dir() / layout.CUTOVER
    if not cutover.exists():
        return Outcome(False, False, ["Not migrated; nothing to roll back"])

    record = journal.for_stamp(cutover.read_text().strip())
    if record is None:
        return Outcome(False, False, [f"No journal for the migration {cutover} names"])

    marker = layout.lemons_dir() / layout.MIGRATING
    try:
        with marker.open("x") as f:  # paused before the check, so nothing changes after it
            f.write(record.directory.name + "\n")
    except FileExistsError:
        return Outcome(False, False, ["A migration is in progress; finish or abort it first"])

    guard.drain()
    if refused := _refusal(record):
        marker.unlink()
        return Outcome(
            False,
            False,
            [
                f"Refused; nothing changed: {refused}.",
                f"The old home is kept at {record.backup}; recover from it by hand if needed.",
            ],
        )

    with db.connect() as conn:
        journal.rewrite_paths(conn, record, forward=False)
    os.rename(record.backup, record.old)
    kept = record.directory / "rolled-back"
    for entry in record.files():  # moved aside, never deleted: a late save survives here
        target: Path = inventory.destination(record.old, entry.relative)
        if target.is_file():
            (kept / entry.relative).parent.mkdir(parents=True, exist_ok=True)
            os.rename(target, kept / entry.relative)
    for entry in reversed(record.entries):
        target = inventory.destination(record.old, entry.relative)
        if entry.directory and target.is_dir() and not any(target.iterdir()):
            target.rmdir()
    cutover.unlink()
    marker.unlink()
    return Outcome(
        True, False, [f"Rolled back; {record.old} is active again, the copies kept at {kept}"]
    )
