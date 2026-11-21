"""Carrying out an edit begun in the grove: asking what it needs, then making the change.

The asking reuses the inbox's own dialogs and the changes its own edits, so the two can't drift
apart. Changes run on a worker thread: group edits rewrite brief files, and the grove's event
loop must stay free to draw.
"""

import dataclasses
from collections import abc

from textual.app import App

from ...config import Config
from ...inbox.tui.edits import group_picker
from ...inbox.tui.edits.screens import RenameScreen, SnoozeScreen
from ..tui.picking import Target
from ..tui.rename_dialog import RenameDialog
from . import changes, renames
from .tree_picker import TreePickerScreen


def _in_thread(app: App, work: abc.Callable[[], str], done: abc.Callable[[str], None]) -> None:
    app.run_worker(lambda: app.call_from_thread(done, work()), thread=True, group="grove-edit")


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
            then(lambda until: changes.snooze(target, until)),
        )
    elif target.action == "archive":
        _in_thread(app, lambda: changes.archive(target), done)
    elif target.action == "pin":
        _in_thread(app, lambda: changes.pin(target), done)
    elif target.action == "group":

        def pick(names: list[str]) -> None:
            app.push_screen(
                group_picker.GroupPickerScreen(f"Move {target.name} to a group", names),
                then(lambda name: changes.move(target, name) if name else "no group chosen"),
            )

        app.run_worker(
            lambda: app.call_from_thread(pick, changes.group_names(target)),
            thread=True,
            group="grove-edit",
        )
    elif target.action == "graft":
        app.push_screen(
            TreePickerScreen(f"Put {target.name} on another lemon's tree", target.trees),
            then(lambda onto: changes.graft(target, onto)),
        )
    elif target.action == "color":

        def choose(saved: str) -> None:
            app.push_screen(
                RenameScreen(
                    saved,
                    title=f'Color of "{target.block}"',
                    placeholder="#rrggbb or a name like teal; empty clears",
                ),
                then(lambda wanted: changes.recolor(target, wanted)),
            )

        app.run_worker(
            lambda: app.call_from_thread(choose, changes.saved_color(target)),
            thread=True,
            group="grove-edit",
        )
