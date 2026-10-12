"""Undoable changes to one session's row, each returning the undo entry it captured.

None means there was nothing to change: the row is gone, or already as asked.
"""

from ... import groups
from ...log import get_logger
from .. import db, undo
from .screens import format_wake_time

_log = get_logger("tui")


def _label(n: db.Notification) -> str:
    return n.name or n.channel


def mark_read(notification_id: int) -> undo.Entry | None:
    with db.connect() as conn:
        n = db.get(conn, notification_id)
        if not n:
            return None

        entry = undo.capture(conn, "mark_read", f'Marked read "{_label(n)}"', [notification_id])
        db.mark_read(conn, notification_id)

    _log.info("mark_read: %s", n.channel)
    return entry


def mark_unread(notification_id: int) -> undo.Entry | None:
    with db.connect() as conn:
        n = db.get(conn, notification_id)
        if not n or n.is_unread:
            return None

        entry = undo.capture(conn, "mark_unread", f'Marked unread "{_label(n)}"', [notification_id])
        db.mark_unread(conn, notification_id)

    _log.info("mark_unread: %s", n.channel)
    return entry


def archive(notification_id: int) -> undo.Entry | None:
    with db.connect() as conn:
        n = db.get(conn, notification_id)
        if not n:
            return None

        # archive() touches every row on the channel, so snapshot them all.
        entry = undo.capture(
            conn, "archive", f'Archived "{_label(n)}"', undo.channel_row_ids(conn, notification_id)
        )
        db.archive(conn, notification_id, "user-action")

    _log.info("archive: %s", n.channel)
    return entry


def wake(notification_id: int) -> undo.Entry | None:
    """Return a snoozed session to the inbox."""
    with db.connect() as conn:
        n = db.get(conn, notification_id)
        if not n:
            return None

        entry = undo.capture(
            conn, "unsnooze", f'Woke "{_label(n)}"', undo.channel_row_ids(conn, n.id)
        )
        db.unsnooze(conn, n.channel)

    _log.info("unsnooze: %s", n.channel)
    return entry


def snooze(n: db.Notification, until: float) -> undo.Entry:
    with db.connect() as conn:
        entry = undo.capture(
            conn,
            "snooze",
            f'Snoozed "{_label(n)}" until {format_wake_time(until)}',
            undo.channel_row_ids(conn, n.id),
        )
        db.snooze(conn, n.id, until)

    _log.info("snooze: %s until %.0f", n.channel, until)
    return entry


def rename(n: db.Notification, new_name: str) -> undo.Entry:
    """An empty or blank name clears the row's own name."""
    with db.connect() as conn:
        entry = undo.capture(conn, "rename", f'Renamed "{_label(n)}"', [n.id])
        db.update_name(conn, n.id, new_name.strip() or None)

    return entry


def undo_latest(stack: undo.Stack, entry: undo.Entry) -> list[str] | str:
    """Reverse *entry*, the newest on *stack*: the Groups: lines it left unwritten, or why it can't."""
    try:
        with db.connect() as conn:
            unwritten = groups.editing.undo(conn, entry.group_change) if entry.group_change else []
            restored = undo.restore(conn, entry)
    except groups.store.GroupError as error:
        # A name taken since can be freed again; a group changed since stays changed.
        if isinstance(error, groups.snapshot.Changed):
            stack.pop()
        return f"Can't undo {entry.description}: {error}"

    stack.pop()
    _log.info("undo: %s (%d rows)", entry.action, restored)
    return list(unwritten)
