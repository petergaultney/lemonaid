"""Asking for a group's name or members, then making the edit undoable and redrawing."""

from collections import abc

from .... import brief, groups
from ... import db, undo
from .. import utils
from ..live.inbox_list import InboxList
from ..tables import row_keys
from . import group_picker
from .screens import RenameScreen


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
    inbox.notify(f"{edit.description} — press {utils.undo_key(inbox.config)} to undo")
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


def recolor(inbox: InboxList, group: groups.store.Group) -> None:
    def chosen(wanted: str | None) -> None:
        if wanted is None:
            return

        try:
            if groups.color.parsed(wanted) == group.saved_color:
                return

            with db.connect() as conn:
                edit = groups.editing.recolor(conn, group, wanted)
        except groups.store.GroupError as error:
            inbox.notify(str(error), severity="warning")
            return

        edited(inbox, edit, [f"group:{group.group_id}"])

    inbox.app.push_screen(
        RenameScreen(
            group.saved_color,
            title=f'Color of "{group.name}"',
            placeholder="#rrggbb or a name like teal; empty clears",
        ),
        chosen,
    )


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
