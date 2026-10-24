"""Carrying out an edit begun in the grove: asking what it needs, then making the change.

The asking reuses the inbox's own dialogs and the changes its own edits, so the two can't drift
apart. Changes run on a worker thread: group edits rewrite brief files, and the grove's event
loop must stay free to draw.
"""

import dataclasses
from collections import abc

from textual.app import App

from ... import brief, groups
from ...config import Config
from ...inbox import db, pins
from ...inbox.tui.edits import group_picker, inbox_edits
from ...inbox.tui.edits.screens import RenameScreen, SnoozeScreen
from ..tui.picking import Target
from ..tui.rename_dialog import RenameDialog
from . import renames


def _in_thread(app: App, work: abc.Callable[[], str], done: abc.Callable[[str], None]) -> None:
    app.run_worker(lambda: app.call_from_thread(done, work()), thread=True, group="grove-edit")


def _channels(target: Target) -> list[str]:
    return [target.channel] if target.channel else [channel for channel, _ in target.lemons]


def _live(conn, target: Target) -> list[db.Notification]:
    found = (db.get_by_channel(conn, channel, unread_only=False) for channel in _channels(target))
    return [n for n in found if n is not None]


def _counted(verb: str, done: int, after: str = "") -> str:
    if not done:
        return "no live lemon to change"
    return f"{verb} {done} lemon{'' if done == 1 else 's'}{after}"


def _archive(target: Target) -> str:
    with db.connect() as conn:
        found = _live(conn, target)
    return _counted("archived", sum(inbox_edits.archive(n.id) is not None for n in found))


def _snooze(target: Target, until: float) -> str:
    with db.connect() as conn:
        found = _live(conn, target)
    for n in found:
        inbox_edits.snooze(n, until)
    return _counted("snoozed", len(found))


def _pin(target: Target) -> str:
    """Pin them all, unless all are pinned already: then unpin them."""
    with db.connect() as conn:
        channels = _channels(target)
        pinning = not all(pins.is_pinned(conn, channel) for channel in channels)
        for channel in channels:
            (pins.pin if pinning else pins.unpin)(conn, channel)
    return _counted("pinned" if pinning else "unpinned", len(channels))


def _lemon_id(conn, channel: str) -> str:
    """The ID a group knows a lemon by: its brief's Lemon-ID, else its channel."""
    try:
        return brief.lemon.lemon_id(conn, channel)
    except (LookupError, ValueError, brief.store.ChangedUnderneath):
        return channel


def _members(conn, name: str) -> tuple[str, ...]:
    try:
        return groups.store.find(conn, name).members
    except LookupError:
        return ()


def _move(target: Target, name: str) -> str:
    moved = 0
    try:
        with db.connect() as conn:
            for channel in _channels(target):
                lemon_id = _lemon_id(conn, channel)
                if lemon_id not in _members(conn, name):
                    groups.editing.add(conn, name, lemon_id, channel)
                if target.block and target.block != name:
                    groups.editing.remove(
                        conn, groups.store.find(conn, target.block), lemon_id, channel
                    )
                moved += 1
    except groups.store.GroupError as error:
        return str(error)
    return _counted("moved", moved, f' to "{name}"')


def _group_names(target: Target) -> list[str]:
    with db.connect() as conn:
        return [
            g.name for g in groups.store.all_groups(conn) if g.members and g.name != target.block
        ]


def _recolor(target: Target, wanted: str) -> str:
    try:
        with db.connect() as conn:
            groups.editing.recolor(conn, groups.store.find(conn, target.block), wanted)
    except (LookupError, groups.store.GroupError) as error:
        return str(error)
    return f'recolored "{target.block}"'


def _saved_color(target: Target) -> str:
    with db.connect() as conn:
        return groups.store.find(conn, target.block).saved_color


def ask(
    app: App,
    target: Target,
    done: abc.Callable[[str], None],
    config: Config,
    rename_session: abc.Callable[[str, str], str] | None = None,
) -> None:
    """Ask for what *target*'s edit needs, make it, and tell *done* what happened, for the prompt
    line. *rename_session(old, new)* renames a tmux session; without it, sessions aren't renamed.
    """

    def then(make: abc.Callable[[object], str]) -> abc.Callable[[object], None]:
        return lambda answer: (
            done("") if answer is None else _in_thread(app, lambda: make(answer), done)
        )

    if target.action == "rename":
        what = "lemon" if target.channel else "tmux session"
        app.push_screen(
            RenameDialog(f"Rename {what} {target.name}", target.name),
            then(
                lambda name: renames.apply(dataclasses.replace(target, name=name), rename_session)
            ),
        )
    elif target.action == "snooze":
        app.push_screen(
            SnoozeScreen(
                session_name=target.name,
                presets=config.inbox.snooze_presets,
                day_start=config.inbox.snooze_day_starts,
            ),
            then(lambda until: _snooze(target, until)),
        )
    elif target.action == "archive":
        _in_thread(app, lambda: _archive(target), done)
    elif target.action == "pin":
        _in_thread(app, lambda: _pin(target), done)
    elif target.action == "group":

        def pick(names: list[str]) -> None:
            app.push_screen(
                group_picker.GroupPickerScreen(f"Move {target.name} to a group", names),
                then(lambda name: _move(target, name) if name else "no group chosen"),
            )

        app.run_worker(
            lambda: app.call_from_thread(pick, _group_names(target)),
            thread=True,
            group="grove-edit",
        )
    elif target.action == "color":

        def choose(saved: str) -> None:
            app.push_screen(
                RenameScreen(
                    saved,
                    title=f'Color of "{target.block}"',
                    placeholder="#rrggbb or a name like teal; empty clears",
                ),
                then(lambda wanted: _recolor(target, wanted)),
            )

        app.run_worker(
            lambda: app.call_from_thread(choose, _saved_color(target)),
            thread=True,
            group="grove-edit",
        )
