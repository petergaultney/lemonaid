"""Group edits on the inbox list, and the group and pin keys at its cursor."""

import sqlite3

from .... import brief, groups
from ....log import get_logger
from ... import db, sections
from ..live.inbox_list import InboxList
from ..tables import row_keys
from . import group_dialogs, inbox_pins

_log = get_logger("tui")


def _by_id(conn: sqlite3.Connection, group_id: int) -> groups.store.Group | None:
    return next((g for g in groups.store.all_groups(conn) if g.group_id == group_id), None)


def selected_group(inbox: InboxList) -> groups.store.Group | None:
    """The group whose header is under the cursor."""
    raw = row_keys.at_cursor(inbox.main)
    found = sections.group_id(raw) if raw else None
    if found is None:
        return None

    with db.connect() as conn:
        return _by_id(conn, found)


def toggle_group(inbox: InboxList, group_id: int, from_row: str = "") -> None:
    """Collapse an open group to its header, or open a collapsed one.

    Collapsing from one of its lemons keeps that lemon drawn, under the
    cursor, until the cursor moves off it.
    """
    with db.connect() as conn:
        group = _by_id(conn, group_id)
        if group is None:
            return

        groups.arrangement.set_collapsed(conn, group, not group.collapsed)

    inbox.kept = frozenset({from_row} if from_row and not group.collapsed else ())
    inbox.redraw()
    inbox.select_key(from_row or f"group:{group_id}")


def toggle_group_at_cursor(inbox: InboxList) -> None:
    """Open or collapse the group whose header or lemon is under the cursor."""
    raw = row_keys.at_cursor(inbox.main) or ""
    if (found := sections.group_id(raw)) is not None:
        toggle_group(inbox, found)
        return

    if (found := sections.row_group_id(raw)) is not None:
        toggle_group(inbox, found, from_row=raw)


def move_group(inbox: InboxList, group: groups.store.Group, offset: int) -> str:
    """Trade places with the group header *offset* away on screen; a refusal's reason.

    Groups are drawn in their saved order, independent of member status.
    """
    table = inbox.main
    on_screen = [
        found
        for row in range(table.row_count)
        if (key := row_keys.at_row(table, row)) is not None
        and (found := sections.group_id(str(key.value))) is not None
    ]
    neighbour = on_screen.index(group.group_id) + offset
    if not 0 <= neighbour < len(on_screen):
        return ""

    with db.connect() as conn:
        other = _by_id(conn, on_screen[neighbour])
        if other is None:
            return ""

        groups.arrangement.swap(conn, group, other)

    inbox.redraw()
    inbox.select_key(f"group:{group.group_id}")
    return ""


def delete_group(inbox: InboxList, group: groups.store.Group) -> None:
    with db.connect() as conn:
        edit = groups.editing.delete(conn, group)
    group_dialogs.edited(inbox, edit)


def group_remove(
    inbox: InboxList, group_id: int, notification: db.Notification, lemon_id: str
) -> None:
    """Take the lemon out of the group it's drawn in."""
    with db.connect() as conn:
        group = _by_id(conn, group_id)
        if group is None:
            return

        edit = groups.editing.remove(
            conn, group, lemon_id, notification.name or notification.channel
        )

    group_dialogs.edited(inbox, edit)


def lemon(inbox: InboxList, notification: db.Notification) -> tuple[db.Notification, str] | None:
    """The row's notification and Lemon-ID, when it has a brief to group it by."""
    with db.connect() as conn:
        try:
            lemon_id = brief.lemon.lemon_id(conn, notification.channel)
        except (LookupError, ValueError, brief.store.ChangedUnderneath):
            inbox.notify("This session has no brief, so it can't be in a group")
            return None

    return notification, lemon_id


def _notification_at_cursor(inbox: InboxList) -> db.Notification | None:
    return row_keys.notification(row_keys.notification_at_cursor(inbox.main))


def pin_at_cursor(inbox: InboxList) -> None:
    if notification := _notification_at_cursor(inbox):
        inbox_pins.toggle_pin(inbox, notification.channel)


def move_at_cursor(inbox: InboxList, offset: int) -> None:
    """Move the group whose header is under the cursor, else the pinned lemon, *offset* places."""
    if group := selected_group(inbox):
        if refused := move_group(inbox, group, offset):
            inbox.notify(refused)
        return

    notification = _notification_at_cursor(inbox)
    if notification and inbox_pins.move_pin(
        inbox, notification.channel, row_keys.channels(inbox.main), offset
    ):
        row_keys.select_channel(inbox.main, notification.channel)


def _lemon_at_cursor(inbox: InboxList) -> tuple[db.Notification, str] | None:
    notification = _notification_at_cursor(inbox)
    return lemon(inbox, notification) if notification else None


def tree_at_cursor(inbox: InboxList) -> None:
    if found := _lemon_at_cursor(inbox):
        group_dialogs.group_tree(inbox, *found)


def add_at_cursor(inbox: InboxList) -> None:
    if found := _lemon_at_cursor(inbox):
        group_dialogs.group_add(inbox, *found)


def recolor_at_cursor(inbox: InboxList) -> None:
    """Ask for a color for the group whose header, or one of whose lemons, is under the cursor."""
    if group := selected_group(inbox):
        group_dialogs.recolor(inbox, group)
        return

    group_id = sections.row_group_id(row_keys.at_cursor(inbox.main) or "")
    if group_id is None:
        return

    with db.connect() as conn:
        group = _by_id(conn, group_id)
    if group:
        group_dialogs.recolor(inbox, group)


def remove_at_cursor(inbox: InboxList) -> None:
    """Take the lemon out of the group it's drawn in; on a header, delete the group."""
    if group := selected_group(inbox):
        delete_group(inbox, group)
        return

    group_id = sections.row_group_id(row_keys.at_cursor(inbox.main) or "")
    if group_id is not None and (found := _lemon_at_cursor(inbox)):
        group_remove(inbox, group_id, *found)
