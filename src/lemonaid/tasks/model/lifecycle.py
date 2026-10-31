"""What happens to a task itself: its subject URL, results, closing and reopening.

These run inside a caller's `ledger.transaction`.
"""

import sqlite3
import typing as ty

from . import ids, ledger


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
