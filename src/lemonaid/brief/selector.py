"""Which lemon a `brief` command means: `--self`, `--session S[:W]`, `--channel`, or `--id`.

`--self` is resolved by `inbox.self_session`, the same as `inbox emoji --self`:
the one live channel recorded at the pane's tty, tmux session, and window.
`--session` picks the one live lemon in a tmux session, or in one window of it
when the session holds several; a window with no lemon yet is a pending target,
for the next lemon to start or be placed there. A Codex on the shared
app-server can't be placed, so a window running one is an error naming
candidates for `--channel`. A window is named by index or by name; a
name must be one tmux knows now.
"""

import argparse
import dataclasses
import os
import sqlite3
import subprocess

from ..inbox import db, self_session
from ..lemon_watchers import watcher
from . import session

_HARNESSES = ("claude", "codex")
_PS_TIMEOUT_SECONDS = 2


@dataclasses.dataclass(frozen=True)
class Selected:
    channel: str  # "" when the target is a window no lemon has started in yet
    tmux_session: str
    tmux_window: str  # tmux's index
    tmux_window_id: str = ""  # tmux's stable ID, when a pending target's window exists


def _live_rows(conn: sqlite3.Connection, where: str, params: tuple) -> list[db.Notification]:
    rows = conn.execute(
        f"SELECT * FROM notifications WHERE status != 'archived' AND {where} "
        "ORDER BY created_at DESC",
        params,
    ).fetchall()
    return [db.Notification.from_row(row) for row in rows]


def _selected(row: db.Notification) -> Selected:
    return Selected(
        row.channel,
        row.metadata.get("tmux_session") or "",
        str(row.metadata.get("tmux_window") or ""),
    )


def _self(conn: sqlite3.Connection) -> tuple[Selected | None, str]:
    pane_id = os.environ.get("TMUX_PANE", "")
    if not pane_id:
        return None, "Not inside tmux ($TMUX_PANE unset), so there is no session to call self"

    where = self_session.pane_location(pane_id)
    if where is None:
        return None, f"Could not ask tmux about pane {pane_id}"

    channel, error = self_session.resolve(conn, where)
    if not channel:
        return None, error

    return Selected(channel, where.session, where.window), ""


def _running_in(tmux_session: str, index: str) -> list[tuple[str, str, bool]]:
    """(harness, directory, on the shared Codex app-server) of each lemon in the window's panes."""
    return [
        (harness, path, harness == "codex" and _codex_on_daemon(tty))
        for tty, path in session.panes(tmux_session, index)
        for harness in _HARNESSES
        if watcher.process_on_tty(tty, harness)
    ]


def _codex_on_daemon(tty: str) -> bool:
    """Whether the Codex on *tty* was started without `--no-daemon`, or that can't be told.

    Only the Codex executable's own arguments count: the shell and anything else on
    the tty can mention the flag too.
    """
    try:
        result = subprocess.run(
            ["ps", "-t", tty.removeprefix("/dev/"), "-o", "args="],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True

    codex = [
        words
        for words in (line.split() for line in result.stdout.splitlines())
        if words and os.path.basename(words[0]) == "codex"
    ]
    return not codex or any("--no-daemon" not in words for words in codex)


def _unlocated(
    conn: sqlite3.Connection, tmux_session: str, index: str, window_id: str
) -> tuple[Selected | None, str]:
    """A pending target for the window, or why the lemon running there can't claim one.

    A lemon already running but not yet placed claims the brief once the watcher
    records its window, but only when it is the only one there. A Codex on the shared app-server never is, and its
    directory doesn't identify it: another Codex, or one that has exited, can
    share it. So that is an error listing those rows as candidates for --channel.
    """
    running = _running_in(tmux_session, index)
    if len(running) > 1:
        harnesses = ", ".join(harness for harness, _, _ in running)
        return None, (
            f"{tmux_session}:{index} is already running {harnesses}, so a brief waiting on "
            "the window could go to either; pass --channel"
        )

    if not any(on_daemon for _, _, on_daemon in running):
        return Selected("", tmux_session, index, window_id), ""

    dirs = {path for _, path, on_daemon in running if on_daemon}
    candidates = sorted(
        {
            row.channel
            for row in _live_rows(
                conn,
                "channel LIKE 'codex:%' AND json_extract(metadata, '$.tmux_session') IS NULL",
                (),
            )
            if row.metadata.get("cwd") in dirs
        }
    )
    return None, (
        f"A Codex on the shared app-server is running in {tmux_session}:{index}; its inbox "
        "row will never place it there, so it would never claim a brief waiting on the "
        "window. Pass --channel"
        + (
            f" (sessions with no tmux location in its directory: {', '.join(candidates)})"
            if candidates
            else ""
        )
    )


def _session(conn: sqlite3.Connection, spec: str) -> tuple[Selected | None, str]:
    tmux_session, _, window = spec.partition(":")
    rows = _live_rows(conn, "json_extract(metadata, '$.tmux_session') = ?", (tmux_session,))
    if window:
        index, window_id = session.window(tmux_session, window)
        if not index and not window.isdigit():
            return None, f"No window {window!r} in tmux session {tmux_session!r}"

        index = index or window
        rows = [r for r in rows if str(r.metadata.get("tmux_window") or "") == index]
        if not rows:
            return _unlocated(conn, tmux_session, index, window_id)

    if len(rows) == 1:
        return _selected(rows[0]), ""

    if not rows:
        return None, (
            f"No live lemon in tmux session {tmux_session!r}; name a window "
            f"({tmux_session}:<window>) to attach to the next lemon that starts there"
        )

    windows = ", ".join(sorted({f"{tmux_session}:{_selected(r).tmux_window}" for r in rows}))
    return None, f"Several lemons in {tmux_session!r}; name one of {windows}"


def _channel(conn: sqlite3.Connection, channel: str) -> tuple[Selected | None, str]:
    found = db.get_by_channel(conn, channel, unread_only=False)
    return (_selected(found), "") if found else (None, f"No inbox session on channel {channel!r}")


def _id(conn: sqlite3.Connection, notification_id: int) -> tuple[Selected | None, str]:
    found = db.get(conn, notification_id)
    return (_selected(found), "") if found else (None, f"No notification {notification_id}")


def select(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[Selected | None, str]:
    """The lemon *args* names, or an error message."""
    if args.session:
        return _session(conn, args.session)

    if args.channel:
        return _channel(conn, args.channel)

    if args.id is not None:
        return _id(conn, args.id)

    return _self(conn)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--self",
        dest="use_self",
        action="store_true",
        help="The lemon running in this tmux pane (its tty, tmux session, and window)",
    )
    target.add_argument(
        "--session",
        metavar="SESSION[:WINDOW]",
        help="The lemon in this tmux session; name the window when it holds several",
    )
    target.add_argument("--channel", help="An inbox channel, from `inbox list --json`")
    target.add_argument("--id", type=int, help="A notification id, from `inbox list --json`")
