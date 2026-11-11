"""Which inbox rows lost their lemon with the terminal server they ran in.

Loss is judged by server, never by pane: one pane going away on a server that
still runs is someone closing it, while a server that is gone, or replaced by a
newer one on the same socket, took every lemon in it. Each front end says which
of its recorded locations are on a server that is gone.
"""

import sqlite3
from collections import abc

from ..front_end import location, terminals
from ..inbox import db, ended


def _verdicts(rows: abc.Iterable[db.Notification]) -> list[tuple[db.Notification, bool | None]]:
    """Each row with True if its terminal server is gone, False if it runs, None if unknown."""
    by_source: dict[str, list[db.Notification]] = {}
    for row in rows:
        if row.switch_source:
            by_source.setdefault(row.switch_source, []).append(row)

    return [
        (row, verdict)
        for source, group in by_source.items()
        if (terminal := terminals.named(source))
        for row, verdict in zip(group, terminal.lost([row.metadata for row in group]), strict=True)
    ]


def candidates(conn: sqlite3.Connection) -> list[db.Notification]:
    """Every row that may still be a running lemon: active, or snoozed, which only defers
    attention to it."""
    return [*db.get_active(conn), *db.get_snoozed(conn)]


def restorable(rows: abc.Iterable[db.Notification]) -> list[db.Notification]:
    """The rows in *rows* to restore: those `mark` leaves lost (their server is gone, or
    they were marked lost and their server can't be asked now) and their harness reported
    no end of its own, and those whose harness crashed.
    """
    return [
        row
        for row, verdict in _verdicts(rows)
        if not ended.reported(row.metadata)
        and (
            verdict is True
            or (verdict is None and ended.lost(row.metadata))
            or ended.failed(row.metadata)
            or ended.cause(row.metadata) == ended.CRASHED
        )
    ]


def _detail(row: db.Notification) -> str:
    where = location.of(row.metadata, row.switch_source)
    return " ".join(
        f"{key}={value}"
        for key, value in (("workspace", where.workspace), ("slot", where.slot), ("tty", where.tty))
        if value
    )


def _judge(
    conn: sqlite3.Connection, rows: abc.Iterable[db.Notification], by: str
) -> tuple[list[db.Notification], dict[str, str]]:
    """(the rows newly marked lost, the end cause of each channel judged gone with its
    server: `server-lost`, or the end its harness reported)."""
    marked = []
    gone: dict[str, str] = {}
    for row, verdict in _verdicts(rows):
        if verdict is True:
            gone[row.channel] = ended.reported(row.metadata) or ended.SERVER_LOST
        if verdict is True and (cause := ended.reported(row.metadata)):
            db.archive_channel(conn, row.channel, "ended before its server", cause=cause, by=by)
        elif verdict is True and db.mark_lost(conn, row.channel, by, _detail(row)):
            marked.append(row)
        elif verdict is False and ended.lost(row.metadata) and not ended.failed(row.metadata):
            db.clear_lost(conn, row.channel)
    return marked, gone


def mark(conn: sqlite3.Connection, by: str) -> list[db.Notification]:
    """Mark every active row whose server is gone as lost; returns the rows newly marked.

    A lost row that now records a pane on a running server (relinked, or heard from
    without a new registration) is lost no longer, unless a restore of it failed: only
    proof that it runs clears that. A row whose harness reported its own
    end before the server went is archived with that cause instead: it was not lost.
    """
    return _judge(conn, candidates(conn), by)[0]


def gone_with_server(conn: sqlite3.Connection, row: db.Notification, by: str) -> str:
    """The end cause recorded if *row*'s lemon went with its server, judged now as `mark`
    would; "" when its server runs or can't be asked.

    Asked before archiving a row whose pane or process is gone, so a loss is never
    archived in the time between two `mark` passes.
    """
    return _judge(conn, [row], by)[1].get(row.channel, "")
