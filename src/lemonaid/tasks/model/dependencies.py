"""Blocking dependencies between tasks: recording one, refusing a cycle, and releasing the
tasks that wait for one that closed.

Writes run inside a caller's `ledger.transaction`.
"""

import sqlite3

from . import ledger


def waits_for(conn: sqlite3.Connection, task_id: str) -> list[str]:
    return [
        row["child_task_id"]
        for row in conn.execute(
            "SELECT child_task_id FROM task_dependencies"
            " WHERE parent_task_id = ? AND resolved_event_id IS NULL ORDER BY created_event_id",
            (task_id,),
        )
    ]


def path(conn: sqlite3.Connection, start: str, goal: str) -> list[str]:
    """Task IDs from *start* to *goal* along live dependencies, or [] if *goal* isn't reached."""
    trail: dict[str, str] = {start: ""}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        if current == goal:
            found = [current]
            while trail[found[-1]]:
                found.append(trail[found[-1]])
            return found[::-1]

        for child in waits_for(conn, current):
            if child not in trail:
                trail[child] = current
                frontier.append(child)
    return []


def depend(
    conn: sqlite3.Connection,
    parent_task_id: str,
    expected: int,
    child_task_id: str,
    actor: str,
    request_id: str,
    at: float,
) -> int:
    """Record that *parent_task_id* waits for *child_task_id*; returns the parent's new revision."""
    if parent_task_id == child_task_id:
        raise ledger.Refused("a task can't wait for itself")

    child = ledger.state(conn, child_task_id)
    if child is None or child["lifecycle"] == "closed":
        raise ledger.Refused(f"task:{child_task_id} isn't an open task to wait for")

    if cycle := path(conn, child_task_id, parent_task_id):
        raise ledger.Refused(
            f"dependency cycle: {' -> '.join(f'task:{t}' for t in [parent_task_id, *cycle])}"
        )

    event_id, state = ledger.append(
        conn,
        parent_task_id,
        expected,
        "dependency_added",
        {"child_task_id": child_task_id},
        actor,
        request_id,
        at,
    )
    conn.execute(
        "INSERT INTO task_dependencies (parent_task_id, child_task_id, created_event_id)"
        " VALUES (?, ?, ?)",
        (parent_task_id, child_task_id, event_id),
    )
    return state["revision"]


def release(
    conn: sqlite3.Connection, task: str, actor: str, request_id: str, at: float
) -> list[str]:
    """Resolve each open dependency on *task*; returns the parent task IDs."""
    rows = conn.execute(
        "SELECT rowid, parent_task_id FROM task_dependencies"
        " WHERE child_task_id = ? AND resolved_event_id IS NULL",
        (task,),
    ).fetchall()
    for row in rows:
        parent = ledger.state(conn, row["parent_task_id"])
        assert parent is not None
        event_id, _ = ledger.append(
            conn,
            row["parent_task_id"],
            parent["revision"],
            "dependency_resolved",
            {"child_task_id": task},
            actor,
            f"{request_id}:release:{row['parent_task_id']}",
            at,
        )
        conn.execute(
            "UPDATE task_dependencies SET resolved_event_id = ? WHERE rowid = ?",
            (event_id, row["rowid"]),
        )
    return [row["parent_task_id"] for row in rows]


def loop_through(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """The tasks on a dependency cycle through *task_id*, or [] when there is none."""
    for child in waits_for(conn, task_id):
        if found := path(conn, child, task_id):
            return found
    return []
