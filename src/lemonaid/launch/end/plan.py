"""Read-only checks before ending a lemon: the Status its caller expects, and what it runs."""

import dataclasses
import sqlite3
from collections import abc

from ...brief import archive, status
from ...config import Config
from ...inbox import db
from ...watch import lemon_restart, registry
from ..restart import planning
from . import closing, done


def _harness(row: db.Notification | None) -> planning.Owned | None:
    if row is None or not done.running(row):
        return None

    try:
        return planning.owned(row)
    except ValueError as error:
        raise ValueError(f"Cannot tell which process to stop: {error}") from error


def _waiter(waiter: registry.Waiter) -> str:
    return f"{waiter.kind} waiter ({', '.join(waiter.targets)}), pid {waiter.pid}"


def build(
    conn: sqlite3.Connection,
    target: str,
    config: Config,
    expected: abc.Collection[str] = ("done",),
    by: str = "user",
) -> dict:
    """What ending *target* does, on behalf of *by*.

    Raises LookupError for no such lemon, and ValueError when its brief's Status is none of
    *expected*, or its harness can't be told apart from what else runs in its pane.
    """
    found = lemon_restart.named(conn, target)
    if found.brief is None or not found.brief.is_file():
        raise LookupError(f"{found.lemon_id} has no brief")

    state = status.split(found.brief.read_text()).status or done.NO_STATUS
    if state.lower() not in {word.lower() for word in expected}:
        raise ValueError(f"{found.lemon_id}'s Status is {state}, not {' or '.join(expected)}")

    row = db.get_by_channel(conn, found.channel, unread_only=False) if found.channel else None
    owned = _harness(row)
    return {
        "kind": "end",
        "lemon_id": found.lemon_id,
        "channel": found.channel,
        "brief": str(found.brief),
        "by": by,
        "expected": list(expected),
        "card": bool(row and not row.is_archived),
        "sole_session": done.sole_session(conn, row),
        # Top level, as in restart's and move's plans, which recovery reads (`native.recovery_required`).
        "source": dataclasses.asdict(owned.source) if owned else None,
        "pane": dataclasses.asdict(owned.pane) if owned else None,
        "waiters": [_waiter(w) for w in lemon_restart.every(found, registry.running())],
        "archived": archive.is_archived(found.brief),
        "closing": (
            closing.preview(owned.pane, config.places.protected_sessions)
            if owned
            else "leave its pane as it is: its harness has already exited"
        ),
    }
