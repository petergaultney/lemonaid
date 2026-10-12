"""Putting the terminal on a session from the inbox, and what to offer when that fails."""

import shlex
import subprocess
from collections import abc

from textual.widget import Widget

from ... import resume as resume_mod
from ...config import Config
from ...handlers import handle_notification
from ...log import get_logger
from .. import db
from .resume_error import ResumeErrorScreen

_log = get_logger("tui")


def copy_command(widget: Widget, command: str) -> None:
    """Put a resume command on the clipboard, or show it where there is none."""
    try:
        subprocess.run(["pbcopy"], input=command.encode(), check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        widget.notify(f"Resume: {command}", severity="information")
    else:
        widget.notify("Copied resume command to clipboard")


def resume_failed(widget: Widget, command: str, reason: str) -> None:
    _log.warning("resume failed: %s", reason)
    widget.app.push_screen(
        ResumeErrorScreen(
            "Could not resume that session",
            f"{reason} Copy the command to run it in a terminal of your choice.",
            offer="copy the resume command",
            details=command,
        ),
        lambda copy: copy_command(widget, command) if copy else None,
    )


def _no_destination(widget: Widget, notification: db.Notification, cwd: str, command: str) -> None:
    widget.app.push_screen(
        ResumeErrorScreen(
            "No safe tmux destination",
            "Lemonaid could not identify one existing session safely. "
            "Copy this command, then paste it into the session where you want "
            "the lemon to run.",
            offer="copy the resume command",
            details=(
                f"Original directory is gone: {notification.metadata.get('cwd')}. "
                f"The conversation will resume in {cwd}.\n\n{command}"
                if cwd != notification.metadata.get("cwd")
                else command
            ),
        ),
        lambda copy: copy_command(widget, command) if copy else None,
    )


def switch_to(
    widget: Widget,
    notification: db.Notification,
    config: Config,
    archive: abc.Callable[[int], None],
) -> bool:
    """Put the terminal on this session, recreating its pane if it is gone.

    On failure, offer the resume command where one can be built, else to
    `archive` the row.
    """
    # Channel drives cwd-based fallback resolution; name is the
    # session name to reuse if the pane is gone and we respawn.
    if handle_notification(
        {**notification.metadata, "channel": notification.channel, "name": notification.name or ""},
        config,
        switch_source=notification.switch_source,
    ):
        return True

    resume = (
        resume_mod.build_resume_command(config, notification.channel, notification.metadata)
        if notification.switch_source == "tmux"
        else None
    )
    if resume:
        cwd, argv = resume
        _no_destination(widget, notification, cwd, f"cd {shlex.quote(cwd)} && {shlex.join(argv)}")
        return False

    title = "Could not switch to that session"
    message = "Its pane is gone and lemonaid could not recreate one for it."
    _log.warning("%s: %s", title, message)
    widget.app.push_screen(
        ResumeErrorScreen(
            title,
            message + " Open its brief with b, or restore its directory and try again.",
            offer="archive it",
        ),
        lambda archive_it: archive(notification.id) if archive_it else None,
    )
    return False


def resume_unavailable(widget: Widget) -> None:
    widget.app.push_screen(
        ResumeErrorScreen(
            "Resume unavailable",
            "This backend or its saved session details do not provide a resume command. "
            "Press Escape to return, then b to read its brief. Restore its directory "
            "or start the harness manually with the saved session ID.",
        )
    )
