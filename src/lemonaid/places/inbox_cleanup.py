"""Capture toss membership before terminals close, then notify the inbox watcher."""

import os
import sqlite3
from collections import abc
from typing import NamedTuple

from .. import tmux
from ..inbox import db, teardown_evidence
from ..log import get_logger
from . import archive_scope, ownership, windows

_log = get_logger("places.inbox_cleanup")


class Snapshot(NamedTuple):
    daemon_ids: list[int]
    terminals: list[db.Notification]


def capture(
    session: str, places: abc.Sequence[ownership.Place], closing: abc.Iterable[str]
) -> Snapshot:
    try:
        with db.connect() as conn:
            rows = db.get_active(conn)
    except sqlite3.Error as e:
        _log.warning("could not read the inbox for teardown: %s", e)
        return Snapshot([], [])

    return Snapshot(
        archive_scope.doomed_rows(
            rows,
            [place.directory.resolve() for place in places if place.root.destroy and place.exists],
        ),
        archive_scope.closing_rows(
            rows,
            (tmux.navigation.session_ttys(session) if session else set()) | windows.ttys(closing),
            os.environ.get("TMUX", "").split(",")[0],
        ),
    )


def finish(snapshot: Snapshot) -> None:
    try:
        with db.connect() as conn:
            teardown_evidence.record(conn, snapshot.terminals)
            for row_id in snapshot.daemon_ids:
                db.archive(conn, row_id, "place-teardown")
    except sqlite3.Error as e:
        _log.warning("could not record torn-down lemons: %s", e)
