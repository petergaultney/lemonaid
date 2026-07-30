"""Undo stack for inbox state changes.

Only mutations confined to the inbox are undoable: archive, mark-read, snooze,
rename. Actions with effects outside the database (switching to a session,
spawning a resume) are not, because reversing the row would not reverse what
already happened in the terminal.

An entry snapshots the affected rows before the mutation, so undo restores
exactly the prior state rather than inferring it. Snapshots are taken per-row
because archive() and snooze() act on every row sharing a channel, and those
rows may not have shared a status.
"""

import sqlite3
import typing as ty

_MAX_DEPTH: ty.Final = 50

_UNDOABLE_COLUMNS: ty.Final = (
    "status",
    "read_at",
    "created_at",
    "name",
    "metadata",
    "snooze_until",
    "snooze_prev_status",
)


class _RowSnapshot(ty.NamedTuple):
    notification_id: int
    values: tuple[ty.Any, ...]


class Entry(ty.NamedTuple):
    """One undoable action: what it was, what to show, and how to reverse it."""

    action: str
    description: str
    rows: tuple[_RowSnapshot, ...]


def _snapshot_rows(conn: sqlite3.Connection, ids: ty.Iterable[int]) -> tuple[_RowSnapshot, ...]:
    columns = ", ".join(_UNDOABLE_COLUMNS)
    snapshots = []
    for notification_id in ids:
        row = conn.execute(
            f"SELECT {columns} FROM notifications WHERE id = ?", (notification_id,)
        ).fetchone()
        if row:
            snapshots.append(
                _RowSnapshot(notification_id, tuple(row[c] for c in _UNDOABLE_COLUMNS))
            )

    return tuple(snapshots)


def channel_row_ids(conn: sqlite3.Connection, notification_id: int) -> list[int]:
    """All row ids sharing the channel of `notification_id`, including itself.

    Channel-wide mutations need this to snapshot everything they will touch.
    """
    row = conn.execute(
        "SELECT channel FROM notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    if not row:
        return [notification_id]

    return [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM notifications WHERE channel = ?", (row["channel"],)
        ).fetchall()
    ]


def capture(
    conn: sqlite3.Connection,
    action: str,
    description: str,
    ids: ty.Iterable[int],
) -> Entry:
    """Snapshot rows before a mutation. Call this *before* mutating them."""
    return Entry(action=action, description=description, rows=_snapshot_rows(conn, ids))


def restore(conn: sqlite3.Connection, entry: Entry) -> int:
    """Restore the rows in `entry` to their snapshotted state. Returns rows changed."""
    assignments = ", ".join(f"{c} = ?" for c in _UNDOABLE_COLUMNS)
    changed = 0
    for snapshot in entry.rows:
        cursor = conn.execute(
            f"UPDATE notifications SET {assignments} WHERE id = ?",
            (*snapshot.values, snapshot.notification_id),
        )
        changed += cursor.rowcount
    conn.commit()
    return changed


class Stack:
    """Bounded LIFO of undoable actions.

    Held in memory for the lifetime of a TUI session; undo history is
    deliberately not persisted, since a snapshot's meaning decays once other
    processes have written to the same rows.
    """

    def __init__(self, max_depth: int = _MAX_DEPTH) -> None:
        self._entries: list[Entry] = []
        self._max_depth = max_depth

    def __len__(self) -> int:
        return len(self._entries)

    def push(self, entry: Entry) -> None:
        if not entry.rows:
            return

        self._entries.append(entry)
        if len(self._entries) > self._max_depth:
            del self._entries[0]

    def peek(self) -> Entry | None:
        return self._entries[-1] if self._entries else None

    def pop(self) -> Entry | None:
        return self._entries.pop() if self._entries else None
