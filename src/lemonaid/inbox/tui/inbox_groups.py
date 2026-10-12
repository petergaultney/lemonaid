"""Group and pin edits on the inbox list: the dialogs they ask through, and the redraw after."""

from collections import abc

from ... import brief, groups
from ...log import get_logger
from .. import db, pins, sections, undo
from . import bindings, group_picker, row_keys
from .inbox_list import InboxList
from .screens import RenameScreen

_log = get_logger("tui")


def selected_group(inbox: InboxList) -> groups.store.Group | None:
    """The group whose header is under the cursor."""
    raw = row_keys.at_cursor(inbox.main)
    found = sections.group_id(raw) if raw else None
    if found is None:
        return None

    with db.connect() as conn:
        return next((g for g in groups.store.all_groups(conn) if g.group_id == found), None)


def toggle_group(inbox: InboxList, group_id: int, from_row: str = "") -> None:
    """Collapse an open group to its header, or open a collapsed one.

    Collapsing from one of its lemons keeps that lemon drawn, under the
    cursor, until the cursor moves off it.
    """
    with db.connect() as conn:
        group = next((g for g in groups.store.all_groups(conn) if g.group_id == group_id), None)
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

    Groups sort by their most pressing row first, so only the order among
    groups drawn next to each other is the user's to change.
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

    if inbox.group_bands.get(on_screen[neighbour]) != inbox.group_bands.get(group.group_id):
        return "Groups sort by their most pressing lemon; this one can't pass that group"

    with db.connect() as conn:
        other = next(
            (g for g in groups.store.all_groups(conn) if g.group_id == on_screen[neighbour]),
            None,
        )
        if other is None:
            return ""

        groups.arrangement.swap(conn, group, other)

    inbox.redraw()
    inbox.select_key(f"group:{group.group_id}")
    return ""


def edited(inbox: InboxList, edit: groups.editing.Edit, select: abc.Sequence[str] = ()) -> None:
    """Make *edit* undoable, redraw, and put the cursor on the first of *select* drawn.

    A lemon key in *select* stays drawn even in a collapsed group, as one
    collapsed from does, until the cursor leaves it. Otherwise the redraw
    follows the lemon under the cursor wherever it went.
    """
    inbox.undo_stack.push(undo.Entry("group", edit.description, (), edit.change))
    raw = row_keys.at_cursor(inbox.main) or ""
    inbox.kept = frozenset({raw, *(key for key in select if "@" in key)})
    inbox.redraw()
    drawn = [key for key in select if key in inbox.main.rows]
    if drawn:
        inbox.select_key(drawn[0])
    inbox.notify(f"{edit.description} — press {bindings.undo_key(inbox.config)} to undo")
    for path in edit.unwritten:
        inbox.notify(f"Couldn't update the Groups: line in {path}", severity="warning")


def rename(inbox: InboxList, group: groups.store.Group, title: str) -> None:
    def renamed(name: str | None) -> None:
        if name is None or name.strip() == group.name:
            return

        try:
            with db.connect() as conn:
                edit = groups.editing.rename(conn, group, name)
        except groups.store.GroupError as error:
            inbox.notify(str(error), severity="warning")
            return

        edited(inbox, edit, [f"group:{group.group_id}"])

    inbox.app.push_screen(RenameScreen(group.name, title=title, placeholder="Group name"), renamed)


def group_tree(inbox: InboxList, notification: db.Notification, lemon_id: str) -> None:
    """Ask for a name, then make a group of the lemon, its children and theirs."""
    lemon_name = notification.name or brief.identity.brief_description(lemon_id)

    def named(name: str | None) -> None:
        if not name or not name.strip():
            return

        try:
            with db.connect() as conn:
                edit = groups.editing.group_tree(conn, lemon_id, name, lemon_name)
        except groups.store.GroupError as error:
            inbox.notify(str(error), severity="warning")
            return

        assert edit.group
        edited(inbox, edit, [f"{notification.id}@{edit.group.group_id}"])

    inbox.app.push_screen(
        RenameScreen(
            groups.editing.valid_name(lemon_name),
            title="Group this lemon and its children",
            placeholder="Group name, new or existing",
        ),
        named,
    )


def group_add(inbox: InboxList, notification: db.Notification, lemon_id: str) -> None:
    """Put the lemon in a group picked from a list, or a new one."""
    name = notification.name or notification.channel
    with db.connect() as conn:
        names = [
            g.name for g in groups.store.all_groups(conn) if g.members and lemon_id not in g.members
        ]

    def picked(group_name: str | None) -> None:
        if not group_name:
            return

        try:
            with db.connect() as conn:
                edit = groups.editing.add(conn, group_name, lemon_id, name)
        except groups.store.GroupError as error:
            inbox.notify(str(error), severity="warning")
            return

        assert edit.group
        edited(
            inbox,
            edit,
            [f"{notification.id}@{edit.group.group_id}", f"group:{edit.group.group_id}"],
        )

    inbox.app.push_screen(group_picker.GroupPickerScreen(f"Add {name} to a group", names), picked)


def delete_group(inbox: InboxList, group: groups.store.Group) -> None:
    with db.connect() as conn:
        edit = groups.editing.delete(conn, group)
    edited(inbox, edit)


def group_remove(
    inbox: InboxList, group_id: int, notification: db.Notification, lemon_id: str
) -> None:
    """Take the lemon out of the group it's drawn in."""
    with db.connect() as conn:
        group = next((g for g in groups.store.all_groups(conn) if g.group_id == group_id), None)
        if group is None:
            return

        edit = groups.editing.remove(
            conn, group, lemon_id, notification.name or notification.channel
        )

    edited(inbox, edit)


def toggle_pin(inbox: InboxList, channel: str) -> None:
    """Hold the session at its place in the list, or release it."""
    with db.connect() as conn:
        now_pinned = pins.toggle(conn, channel)

    _log.info("pin: %s -> %s", channel, now_pinned)
    inbox.redraw()
    inbox.notify(f"{'Pinned' if now_pinned else 'Unpinned'} {channel}")


def lemon(inbox: InboxList, notification: db.Notification) -> tuple[db.Notification, str] | None:
    """The row's notification and Lemon-ID, when it has a brief to group it by."""
    with db.connect() as conn:
        try:
            lemon_id = brief.lemon.lemon_id(conn, notification.channel)
        except (LookupError, ValueError, brief.store.ChangedUnderneath):
            inbox.notify("This session has no brief, so it can't be in a group")
            return None

    return notification, lemon_id


def move_pin(inbox: InboxList, channel: str, row_channels: abc.Sequence[str], offset: int) -> bool:
    """Trade places with the nearest pinned session `offset` away on screen.

    The neighbour is taken from the rendered list rather than from the pins
    table, so a pinned session that is currently snoozed keeps its position
    and returns between the same two rows it sat between before.
    """
    with db.connect() as conn:
        if not pins.is_pinned(conn, channel):
            return False

        pinned_now = pins.pinned_positions(conn)
        on_screen = [c for c in row_channels if c in pinned_now]
        if channel not in on_screen:
            return False

        neighbour = on_screen.index(channel) + offset
        if not 0 <= neighbour < len(on_screen):
            return False

        pins.swap(conn, channel, on_screen[neighbour])

    inbox.redraw()
    return True


def _notification_at_cursor(inbox: InboxList) -> db.Notification | None:
    return row_keys.notification(row_keys.notification_at_cursor(inbox.main))


def pin_at_cursor(inbox: InboxList) -> None:
    if notification := _notification_at_cursor(inbox):
        toggle_pin(inbox, notification.channel)


def move_at_cursor(inbox: InboxList, offset: int) -> None:
    """Move the group whose header is under the cursor, else the pinned lemon, *offset* places."""
    if group := selected_group(inbox):
        if refused := move_group(inbox, group, offset):
            inbox.notify(refused)
        return

    notification = _notification_at_cursor(inbox)
    if notification and move_pin(
        inbox, notification.channel, row_keys.channels(inbox.main), offset
    ):
        row_keys.select_channel(inbox.main, notification.channel)


def _lemon_at_cursor(inbox: InboxList) -> tuple[db.Notification, str] | None:
    notification = _notification_at_cursor(inbox)
    return lemon(inbox, notification) if notification else None


def tree_at_cursor(inbox: InboxList) -> None:
    if found := _lemon_at_cursor(inbox):
        group_tree(inbox, *found)


def add_at_cursor(inbox: InboxList) -> None:
    if found := _lemon_at_cursor(inbox):
        group_add(inbox, *found)


def remove_at_cursor(inbox: InboxList) -> None:
    """Take the lemon out of the group it's drawn in; on a header, delete the group."""
    if group := selected_group(inbox):
        delete_group(inbox, group)
        return

    group_id = sections.row_group_id(row_keys.at_cursor(inbox.main) or "")
    if group_id is not None and (found := _lemon_at_cursor(inbox)):
        group_remove(inbox, group_id, *found)
