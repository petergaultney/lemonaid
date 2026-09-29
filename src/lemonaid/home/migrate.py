"""Move briefs and messages from `~/.brief-lemons/` to `~/.lemons/`, failing closed.

Every step can be rerun. A step that finds something it can't account for
stops with the migration still paused, and nothing is overwritten: the old
home is renamed, never deleted, and the new home becomes active only when the
last check has passed.
"""

import contextlib
import dataclasses
import datetime
import os
import sqlite3
from pathlib import Path

from ..inbox import db
from . import copying, guard, inventory, journal, layout


@dataclasses.dataclass(frozen=True)
class Outcome:
    done: bool
    paused: bool  # the migration is still in progress and brief commands still wait
    messages: list[str]


def _marker() -> Path:
    return layout.lemons_dir() / layout.MIGRATING


def _stopped(*messages: str) -> Outcome:
    return Outcome(
        False, True, [*messages, "Still paused: rerun `lemonaid home migrate`, or `--abort`."]
    )


def _stamp() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def pause() -> Outcome:
    """Pause brief and message commands ahead of a migration, so waiters can be stopped."""
    marker = _marker()
    if marker.exists():
        return Outcome(False, True, ["Already paused"])

    layout.lemons_dir().mkdir(parents=True, exist_ok=True)
    with marker.open("x") as f:
        f.write(_stamp() + "\n")
    return Outcome(True, True, ["Paused; stop inbox waiters, then `lemonaid home migrate`"])


def _start() -> tuple[journal.Journal | None, Outcome | None]:
    """The journal to continue, or why the migration can't start.

    With no pause in place, one is taken before the check, so no waiter arms in
    between, and lifted again if the check refuses. A pause that was already in
    place stays, since whoever took it is stopping waiters.
    """
    marker = _marker()
    already_paused = marker.exists()
    if already_paused:
        stamp = marker.read_text().strip()
        if record := journal.for_stamp(stamp):
            return record, None
    else:
        stamp = _stamp()
        layout.lemons_dir().mkdir(parents=True, exist_ok=True)
        with marker.open("x") as f:
            f.write(stamp + "\n")

    guard.drain()
    with db.connect() as conn:
        found = inventory.plan(conn)
    if found.blockers:
        if not already_paused:
            marker.unlink()
            return None, Outcome(False, False, ["Refused; nothing changed:", *found.blockers])

        return None, _stopped("Nothing copied yet:", *found.blockers)

    directory = journal.directory_for(stamp)
    directory.mkdir(parents=True, exist_ok=True)
    with (
        db.connect() as conn,
        contextlib.closing(sqlite3.connect(directory / "lemonaid.db")) as backup,
    ):
        conn.backup(backup)
    return journal.create(directory, found), None


def _sources_unchanged(record: journal.Journal) -> str:
    known = {entry.relative for entry in record.entries}
    for entry in record.files():
        if inventory.sha256(record.old / entry.relative) != entry.sha256:
            return f"{record.old / entry.relative} changed after the inventory"

    added = [p for p in record.old.rglob("*") if p.relative_to(record.old).as_posix() not in known]
    return f"{added[0]} was added after the inventory" if added else ""


def _verified(record: journal.Journal) -> str:
    if record.old.exists() or record.old.is_symlink():
        return f"{record.old} was recreated after it was moved aside"

    if unsafe := inventory.unsafe_destinations(
        inventory.destination(record.old, e.relative) for e in record.entries
    ):
        return unsafe[0]

    known = {entry.relative for entry in record.entries}
    added = [
        p for p in record.backup.rglob("*") if p.relative_to(record.backup).as_posix() not in known
    ]
    if added:
        return f"{added[0]} was written to the old home after the inventory"

    for entry in record.files():
        new = inventory.destination(record.old, entry.relative)
        kept = record.backup / entry.relative
        if not (inventory.sha256(kept) == entry.sha256 == inventory.sha256(new)):
            return f"{new} no longer matches {kept}"

    armed = [
        *inventory.armed_waiters(layout.lemons_dir() / "inbox"),
        *inventory.armed_waiters(record.backup / "inbox"),
    ]
    if armed:
        return f"An inbox waiter armed during the migration, for {', '.join(armed)}"

    with db.connect() as conn:
        stale = list(inventory.db_paths(conn, record.old))
    return f"{stale[0][0]} still names {stale[0][1]}" if stale else ""


def run() -> Outcome:
    if (layout.lemons_dir() / layout.CUTOVER).exists():
        return Outcome(False, False, ["Already migrated"])

    record, refused = _start()
    if refused or record is None:
        return refused or _stopped("No journal")

    if record.old.exists():
        if error := copying.copy_all(record) or _sources_unchanged(record):
            return _stopped(error)

        with db.connect() as conn:
            journal.rewrite_paths(conn, record, forward=True)
        if record.backup.exists():
            return _stopped(f"{record.backup} already exists")

        os.rename(record.old, record.backup)

    if error := _verified(record):
        return _stopped(error)

    journal.write_atomic(layout.lemons_dir() / layout.CUTOVER, record.directory.name + "\n")
    _marker().unlink()
    if stray := layout.stray():  # a save between verification and the marker
        return Outcome(False, False, [f"Cut over, but {stray}"])

    return Outcome(True, False, [f"Migrated; the old home is kept at {record.backup}"])


def abort() -> Outcome:
    """Undo a migration that hasn't yet moved the old home aside."""
    marker = _marker()
    if not marker.exists():
        return Outcome(False, False, ["No migration in progress"])

    if marker.read_text().startswith("reconcile"):
        return _stopped("A reconciliation is paused; finish it with `--reconcile`")

    record = journal.for_stamp(marker.read_text().strip())
    if record is None:
        marker.unlink()
        return Outcome(False, False, ["Aborted before anything was copied"])

    if not record.old.exists():
        return _stopped(f"{record.old} is already moved aside; rerun to finish instead")

    if unsafe := inventory.unsafe_destinations(
        inventory.destination(record.old, e.relative) for e in record.entries
    ):
        return _stopped(f"{unsafe[0]}; remove the copies by hand")

    with db.connect() as conn:
        journal.rewrite_paths(conn, record, forward=False)
    copying.remove_partials(record)
    for entry in reversed(record.entries):
        target = inventory.destination(record.old, entry.relative)
        if entry.directory:
            if target.is_dir() and not any(target.iterdir()):
                target.rmdir()
        elif target.is_file() and inventory.sha256(target) == entry.sha256:
            target.unlink()
    marker.unlink()
    return Outcome(
        False, False, [f"Aborted; {record.old} is active, journal kept at {record.directory}"]
    )
