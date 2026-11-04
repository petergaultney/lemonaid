"""What happens to a task itself: its subject URL, results, closing and reopening.

These run inside a caller's `ledger.transaction`.
"""

import sqlite3
import typing as ty

from . import dependencies, ids, ledger


def set_url(
    conn: sqlite3.Connection,
    task: str,
    expected: int,
    url: str,
    reason: str,
    actor: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    if not reason.strip():
        raise ValueError("changing a task's URL needs a reason")

    current = ledger.state(conn, task)
    previous = current["subject_url"] if current else ""
    _, state = ledger.append(
        conn,
        task,
        expected,
        "url_set",
        {"url": ids.subject_url(url), "previous": previous, "reason": reason.strip()},
        actor,
        request_id,
        at,
    )
    return {"task_id": task, "revision": state["revision"], "previous_url": previous}


def result(
    conn: sqlite3.Connection,
    task: str,
    expected: int,
    evidence: str,
    actor: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    """Record a result without closing the task."""
    if not evidence.strip():
        raise ValueError("a result needs evidence: a commit, PR, document or brief reference")

    _, state = ledger.append(
        conn, task, expected, "result", {"evidence": evidence.strip()}, actor, request_id, at
    )
    return {"task_id": task, "revision": state["revision"]}


def request_recheck(
    conn: sqlite3.Connection, task: str, expected: int, actor: str, request_id: str, at: float
) -> dict[str, ty.Any]:
    """Record that someone asked for the task's holder to re-check its Status; the checker
    sees it as `recheck.requested_at` and decides what, if anything, to send."""
    _, state = ledger.append(conn, task, expected, "recheck_requested", {}, actor, request_id, at)
    return {"task_id": task, "holder": state["holder"], "revision": state["revision"]}


def close(
    conn: sqlite3.Connection,
    task: str,
    expected: int,
    reason: str,
    actor: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    """Close the task and release every task waiting for it; returns those as `released`."""
    current = ledger.state(conn, task)
    if current is None:
        raise LookupError(f"no task:{task}")

    if current["lifecycle"] == "closed":
        raise ValueError(f"task:{task} is already closed")

    if not reason.strip():
        raise ValueError("closing a task needs a reason")

    _, state = ledger.append(
        conn, task, expected, "closed", {"reason": reason.strip()}, actor, request_id, at
    )
    return {
        "task_id": task,
        "revision": state["revision"],
        "holder": state["holder"],
        "released": dependencies.release(conn, task, actor, request_id, at),
    }


def reopen(
    conn: sqlite3.Connection,
    task: str,
    expected: int,
    reason: str,
    actor: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    """Reopen a closed task with its last holder; released dependencies stay released."""
    current = ledger.state(conn, task)
    if current is None:
        raise LookupError(f"no task:{task}")

    if current["lifecycle"] != "closed":
        raise ValueError(f"task:{task} is already open")

    if not reason.strip():
        raise ValueError("reopening a task needs a reason")

    _, state = ledger.append(
        conn, task, expected, "reopened", {"reason": reason.strip()}, actor, request_id, at
    )
    return {"task_id": task, "revision": state["revision"], "holder": state["holder"]}
