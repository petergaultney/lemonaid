"""Tell an archived session that is still running from one that has exited.

The watcher archives on evidence gathered from outside a session, and that
evidence can be wrong. History uses the same two checks the watcher archives
on, a pane on the recorded tty and the harness process running there, to
decide whether Enter should switch to a session or resume it.
"""

import sqlite3
import time
from collections import abc

from ..handlers import check_pane_exists_by_tty
from ..lemon_watchers import watcher
from . import db


def running(n: db.Notification) -> bool:
    """Whether `n`'s pane and harness process are still on its recorded tty.

    Asked of the tmux server the session was recorded on, and a pane in a tmux
    session younger than the record does not count, since ttys are reused.
    """
    tty = n.metadata.get("tty")
    if not tty or not n.switch_source:
        return False

    pane = check_pane_exists_by_tty(
        tty, n.switch_source, n.metadata.get("tmux_socket"), n.created_at
    )
    return pane is True and watcher.is_process_running_on_tty(
        tty, watcher.harness_process(n.channel)
    )


def restore(conn: sqlite3.Connection, channel: str) -> int:
    """Make every archived row on `channel` unread, and its newest row newest on its tty.

    The watcher keeps only the newest session on a tty and archives the rest, so
    a restored session keeping its old age would be archived again on the next
    tick by whatever displaced it. Only the highest-id row moves, since that is
    the row the inbox shows, and `db.add` updates whichever row is newest by
    `created_at`. Returns rows changed.
    """
    cursor = conn.execute(
        """
        UPDATE notifications SET status = 'unread', read_at = NULL,
            created_at = CASE
                WHEN id = (SELECT MAX(id) FROM notifications WHERE channel = ?) THEN ?
                ELSE created_at
            END
        WHERE channel = ? AND status = 'archived'
        """,
        (channel, time.time(), channel),
    )
    conn.commit()
    return cursor.rowcount


def restore_focused(conn: sqlite3.Connection, ttys: abc.Iterable[str]) -> list[str]:
    """Bring back, as read, each session on `ttys` that was archived while still running there.

    Only when the newest row recorded on the tty is archived, so a session the
    inbox already shows there is never displaced. Returns the channels restored.
    """
    restored = []
    for tty in ttys:
        row = conn.execute(
            "SELECT * FROM notifications WHERE json_extract(metadata, '$.tty') = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (tty,),
        ).fetchone()
        if row is None or row["status"] != "archived":
            continue

        n = db.Notification.from_row(row)
        if not running(n):
            continue

        restore(conn, n.channel)
        conn.execute(
            "UPDATE notifications SET status = 'read', read_at = ? "
            "WHERE channel = ? AND status = 'unread'",
            (time.time(), n.channel),
        )
        conn.commit()
        restored.append(n.channel)
    return restored
