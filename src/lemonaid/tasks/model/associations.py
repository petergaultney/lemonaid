"""Brief-task associations and standing exemptions.

These run inside a caller's `ledger.transaction`. Each writes its event first and its
normalized row with that event's ID, so the row and the log agree.
"""

import sqlite3
import typing as ty

from . import identities, ledger

KINDS = frozenset({"holder", "observer"})


def _of(conn: sqlite3.Connection, brief_id: str, kind: str) -> list[str]:
    names = identities.names(conn, brief_id)
    return [
        row["task_id"]
        for row in conn.execute(
            "SELECT task_id FROM brief_tasks WHERE kind = ?"
            f" AND brief_id IN ({identities.placeholders(names)}) ORDER BY created_event_id",
            [kind, *names],
        )
    ]


def held_of(conn: sqlite3.Connection, brief_id: str) -> list[str]:
    """Tasks *brief_id* holds or has held."""
    return _of(conn, brief_id, "holder")


def observed_of(conn: sqlite3.Connection, brief_id: str) -> list[str]:
    return _of(conn, brief_id, "observer")


def exemption_of(conn: sqlite3.Connection, brief_id: str) -> str:
    names = identities.names(conn, brief_id)
    row = conn.execute(
        "SELECT reason FROM brief_task_exemptions"
        f" WHERE brief_id IN ({identities.placeholders(names)})",
        names,
    ).fetchone()
    return row["reason"] if row else ""


def record_link(
    conn: sqlite3.Connection, brief_id: str, task_id: str, kind: str, event_id: int
) -> None:
    """The `brief_tasks` row for an event that already records the association. Holding
    a task replaces observing it; a brief that hands it on observes it (`handed_on`)."""
    if kind not in KINDS:
        raise ledger.Refused(f"association kind {kind!r}")

    conn.execute(
        "INSERT INTO brief_tasks (brief_id, task_id, kind, created_event_id) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (brief_id, task_id) DO UPDATE SET kind = 'holder'"
        " WHERE excluded.kind = 'holder'",
        (brief_id, task_id, kind, event_id),
    )


def observe(
    conn: sqlite3.Connection,
    task_id: str,
    expected: int,
    brief_id: str,
    actor: str,
    request_id: str,
    at: float,
) -> int:
    """Link *brief_id* to a task without changing its holder; returns the new revision."""
    event_id, state = ledger.append(
        conn,
        task_id,
        expected,
        "linked",
        {"brief_id": brief_id, "kind": "observer"},
        actor,
        request_id,
        at,
    )
    record_link(conn, brief_id, task_id, "observer", event_id)
    return state["revision"]


def handed_on(conn: sqlite3.Connection, brief_id: str, task_id: str) -> None:
    """*brief_id* gave its task away, so it observes it now; the `assigned` event that
    moved the task records this, through its previous holder."""
    conn.execute(
        "UPDATE brief_tasks SET kind = 'observer' WHERE brief_id = ? AND task_id = ?",
        (brief_id, task_id),
    )


def unobserve(
    conn: sqlite3.Connection,
    task_id: str,
    expected: int,
    brief_id: str,
    actor: str,
    request_id: str,
    at: float,
) -> int:
    """Stop *brief_id* observing a task; returns the new revision. The holder can't."""
    names = identities.names(conn, brief_id)
    linked = conn.execute(
        "SELECT brief_id FROM brief_tasks WHERE task_id = ? AND kind = 'observer'"
        f" AND brief_id IN ({identities.placeholders(names)})",
        [task_id, *names],
    ).fetchall()
    if not linked:
        raise ledger.Refused(f"{brief_id} doesn't observe task:{task_id}")

    _, state = ledger.append(
        conn, task_id, expected, "unlinked", {"brief_id": brief_id}, actor, request_id, at
    )
    conn.executemany(
        "DELETE FROM brief_tasks WHERE brief_id = ? AND task_id = ?",
        [(row["brief_id"], task_id) for row in linked],
    )
    return state["revision"]


def exempt(
    conn: sqlite3.Connection, brief_id: str, reason: str, checker_id: str, at: float
) -> None:
    if not reason.strip():
        raise ledger.Refused("a standing exemption needs a reason")

    if held := held_of(conn, brief_id):
        raise ledger.Refused(f"{brief_id} has held task:{held[0]}; it can't also be exempt")

    conn.execute(
        "INSERT INTO brief_task_exemptions (brief_id, reason, checker_id, created_at, revision)"
        " VALUES (?, ?, ?, ?, 1)"
        " ON CONFLICT (brief_id) DO UPDATE SET reason = excluded.reason,"
        " checker_id = excluded.checker_id, created_at = excluded.created_at,"
        " revision = brief_task_exemptions.revision + 1",
        (brief_id, reason.strip(), checker_id, at),
    )


def links_of(conn: sqlite3.Connection, task_id: str) -> list[dict[str, ty.Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT brief_id, kind FROM brief_tasks WHERE task_id = ? ORDER BY created_event_id",
            (task_id,),
        )
    ]
