"""Start an archived session again in tmux and bring its row back to the inbox."""

import sqlite3

from .. import resume, tmux
from ..config import Config
from ..log import get_logger
from . import db, unarchive

_log = get_logger("inbox.resume_archived")


def recorded_here(conn: sqlite3.Connection, channel: str, tty: str) -> None:
    """Record that `channel` runs on `tty` of the tmux server this process runs under."""
    socket = tmux.navigation.current_socket()
    location = (tmux.navigation.locations_by_tty(socket) or {}).get(tty)
    unarchive.moved(conn, channel, tty, socket, location)


def _returned(channel: str, tty: str | None) -> None:
    with db.connect() as conn:
        if tty:
            recorded_here(conn, channel, tty)
        unarchive.restore(conn, channel)


def in_new_session(n: db.Notification, config: Config) -> str | None:
    """Resume `n` in a tmux session of its own. Returns why it could not, or None."""
    resumable = resume.build_resume_command(config, n.channel, n.metadata)
    if resumable is None:
        return "No working directory is recorded for it, so there is nowhere to resume it."

    cwd, argv = resumable
    error, tty = tmux.session.spawn_resumed(
        cwd, config.tmux_session, argv, n.channel, n.metadata, n.name or ""
    )
    if error:
        return error

    _returned(n.channel, tty)
    return None


def in_tmux(n: db.Notification, config: Config) -> str | None:
    """Resume `n` in a new window of its own tmux session, or in a new session when
    no existing one can be identified safely. Returns why it could not, or None."""
    tty = tmux.recreate.resume({**n.metadata, "channel": n.channel}, config)
    if tty is None:
        _log.info("no existing tmux session for %s; starting one", n.channel)
        return in_new_session(n, config)

    _returned(n.channel, tty)
    return None
