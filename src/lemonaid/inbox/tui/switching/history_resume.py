"""Resuming a session from the history list: what to run, and where."""

import dataclasses
import shlex
import time
import typing as ty

from .... import resume
from ....config import Config
from ....log import get_logger
from ... import db, resume_archived, unarchive

_log = get_logger("tui")

Mode = ty.Literal["copy", "tmux", "exec"]


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What the app shows or does next.

    `running`: the session never stopped and is back in the inbox.
    `unresumable`: nothing is recorded to resume it with.
    `failed`: starting it failed for `reason`; `command` runs it by hand.
    `started`: it is running in a new tmux window or session.
    `exec`: run `argv` in `cwd` in place of this app.
    `copy`: hand `command` to the user.
    """

    kind: ty.Literal["running", "unresumable", "failed", "started", "exec", "copy"]
    command: str = ""
    reason: str = ""
    cwd: str = ""
    argv: tuple[str, ...] = ()


def run(notification: db.Notification, config: Config, mode: Mode, here_tty: str) -> Outcome:
    """`here_tty` is this terminal's tty when it is a tmux pane, where an exec would run."""
    # A session that never stopped needs returning to the inbox, not a
    # second copy of itself started next to the one already running.
    if mode != "copy" and unarchive.running(notification):
        with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
            unarchive.restore(conn, notification.channel)
        return Outcome("running")

    found = resume.build_resume_command(config, notification.channel, notification.metadata)
    if not found:
        return Outcome("unresumable")

    cwd, argv = found
    command = (
        f"cd {shlex.quote(cwd)} && {' '.join(shlex.quote(a) for a in argv)}"
        if argv
        else f"cd {shlex.quote(cwd)}"
    )
    _log.info("resume: %s (%s) -> %s", notification.channel, mode, command)

    # The scratch pane has no terminal of its own to run the session in.
    if mode == "tmux" and argv:
        error = resume_archived.in_tmux(notification, config)
        return Outcome("failed", command, error) if error else Outcome("started")

    # Before the row is unread, or the watcher judges it by its dead pane.
    if mode == "exec" and argv and here_tty:
        with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
            resume_archived.recorded_here(conn, notification.channel, here_tty)

    # Unarchive so the session appears in the main inbox immediately
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        conn.execute(
            "UPDATE notifications SET status = 'unread', read_at = NULL, created_at = ? WHERE id = ?",
            (time.time(), notification.id),
        )
        conn.commit()

    if mode == "exec" and argv:
        return Outcome("exec", command, cwd=cwd, argv=tuple(argv))

    return Outcome("copy", command)


def in_new_session(notification: db.Notification, config: Config) -> Outcome:
    """Spawn a new tmux session around the session."""
    found = resume.build_resume_command(config, notification.channel, notification.metadata)
    if not found:
        return Outcome("unresumable")

    cwd, argv = found
    error = resume_archived.in_new_session(notification, config)
    if error:
        return Outcome("failed", f"cd {shlex.quote(cwd)} && {shlex.join(argv)}", error)

    return Outcome("started")
