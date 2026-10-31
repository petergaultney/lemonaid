"""Writing task events: each append checks the expected revision and updates `tasks` with it.

Callers hold `transaction` around a whole operation, so its events, the associations they
imply and its request record commit together or not at all.
"""

import contextlib
import hashlib
import json
import sqlite3
import typing as ty
from collections import abc

from . import events


class Conflict(Exception):
    def __init__(self, task_id: str, expected: int, current: events.State) -> None:
        super().__init__(
            f"task:{task_id} is at revision {current['revision']}, held by"
            f" {current['holder']}; expected revision {expected}"
        )
        self.current = current


class RequestReused(ValueError):
    pass


class Refused(ValueError):
    pass


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> abc.Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def state(conn: sqlite3.Connection, task_id: str) -> events.State | None:
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def history(conn: sqlite3.Connection, task_id: str) -> list[dict[str, ty.Any]]:
    return [
        {**dict(row), "data": json.loads(row["data"])}
        for row in conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY revision", (task_id,)
        )
    ]


def _write(
    conn: sqlite3.Connection,
    task_id: str,
    previous: events.State | None,
    kind: str,
    data: ty.Mapping[str, ty.Any],
    actor: str,
    request_id: str,
    at: float,
) -> tuple[int, events.State]:
    revision = previous["revision"] + 1 if previous else 1
    event_id = conn.execute(
        "INSERT INTO task_events (task_id, revision, kind, actor, at, request_id, data)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, revision, kind, actor, at, request_id, json.dumps(data, sort_keys=True)),
    ).lastrowid
    assert event_id is not None
    event = {"event_id": event_id, "revision": revision, "kind": kind, "at": at, "data": data}
    new = events.apply(task_id, previous, event)
    conn.execute(
        f"INSERT OR REPLACE INTO tasks ({', '.join(events.COLUMNS)})"
        f" VALUES ({', '.join('?' for _ in events.COLUMNS)})",
        tuple(new[c] for c in events.COLUMNS),
    )
    return event_id, new


def create(
    conn: sqlite3.Connection,
    task_id: str,
    data: ty.Mapping[str, ty.Any],
    actor: str,
    request_id: str,
    at: float,
) -> tuple[int, events.State]:
    return _write(conn, task_id, None, "created", data, actor, request_id, at)


def append(
    conn: sqlite3.Connection,
    task_id: str,
    expected: int,
    kind: str,
    data: ty.Mapping[str, ty.Any],
    actor: str,
    request_id: str,
    at: float,
) -> tuple[int, events.State]:
    """Raises LookupError for an unknown task and Conflict unless it is at *expected*."""
    current = state(conn, task_id)
    if current is None:
        raise LookupError(f"no task:{task_id}")

    if current["revision"] != expected:
        raise Conflict(task_id, expected, current)

    return _write(conn, task_id, current, kind, data, actor, request_id, at)


def once(
    conn: sqlite3.Connection,
    request_id: str,
    operation: ty.Mapping[str, ty.Any],
    run: abc.Callable[[], dict[str, ty.Any]],
) -> dict[str, ty.Any]:
    """*run*'s result, or the result already stored for *request_id* if it committed before.

    Raises RequestReused when *request_id* was used for a different operation.
    """
    fingerprint = hashlib.sha256(json.dumps(operation, sort_keys=True).encode()).hexdigest()
    row = conn.execute(
        "SELECT fingerprint, result FROM task_requests WHERE request_id = ?", (request_id,)
    ).fetchone()
    if row:
        if row["fingerprint"] != fingerprint:
            raise RequestReused(f"request {request_id} was already used for another operation")

        return json.loads(row["result"])

    result = run()
    conn.execute(
        "INSERT INTO task_requests (request_id, fingerprint, result) VALUES (?, ?, ?)",
        (request_id, fingerprint, json.dumps(result, sort_keys=True)),
    )
    return result


def consistent(conn: sqlite3.Connection, task_id: str) -> bool:
    """Whether replaying the task's events reproduces its `tasks` row."""
    return events.fold(task_id, history(conn, task_id)) == state(conn, task_id)
