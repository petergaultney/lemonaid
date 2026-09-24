"""Which lemon a `brief` command means: `--self`, `--session S[:W]`, `--channel`, or `--id`.

`--self` is resolved by `inbox.self_session`, the same as `inbox emoji --self`:
the one live channel recorded at the pane's tty, tmux session, and window.
`--session` picks the one live lemon in a tmux session, or in one window of it
when the session holds several; a window with no lemon yet is a pending target,
for the next lemon to start there.
"""

import argparse
import dataclasses
import os
import sqlite3

from ..inbox import db, self_session


@dataclasses.dataclass(frozen=True)
class Selected:
    channel: str  # "" when the target is a window no lemon has started in yet
    tmux_session: str
    tmux_window: str


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


def _session(conn: sqlite3.Connection, spec: str) -> tuple[Selected | None, str]:
    tmux_session, _, window = spec.partition(":")
    rows = _live_rows(conn, "json_extract(metadata, '$.tmux_session') = ?", (tmux_session,))
    if window:
        rows = [r for r in rows if str(r.metadata.get("tmux_window") or "") == window]
        if not rows:
            return Selected("", tmux_session, window), ""

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
