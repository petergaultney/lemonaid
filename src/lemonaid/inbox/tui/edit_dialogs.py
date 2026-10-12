"""The dialogs that ask how to change a session's row, then make the change."""

from collections import abc

from textual.app import App

from ...config import Config
from .. import db, undo
from . import inbox_edits
from .screens import RenameScreen, SnoozeScreen


def snooze(
    app: App, notification: db.Notification, config: Config, done: abc.Callable[[undo.Entry], None]
) -> None:
    """Ask how long to snooze the session for; `done` gets the change once made."""

    def snoozed(until: float | None) -> None:
        if until is not None:
            done(inbox_edits.snooze(notification, until))

    app.push_screen(
        SnoozeScreen(
            session_name=notification.name or "",
            presets=config.inbox.snooze_presets,
            day_start=config.inbox.snooze_day_starts,
        ),
        snoozed,
    )


def rename(app: App, notification: db.Notification, done: abc.Callable[[undo.Entry], None]) -> None:
    """Ask for the session's new name; `done` gets the change once made."""

    def renamed(new_name: str | None) -> None:
        if new_name is not None:
            done(inbox_edits.rename(notification, new_name))

    app.push_screen(RenameScreen(current_name=notification.name or ""), renamed)
