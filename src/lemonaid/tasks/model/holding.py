"""Who holds a task: creating it with a holder, handing it on, its holder's lemon
starting, and the open tasks a brief holds.

These run inside a caller's `ledger.transaction`. Brief IDs passed here are already
resolved to current Lemon-IDs; a holder is a tagged string, `brief:ID`.
"""

import sqlite3
import typing as ty
import uuid

from . import associations, identities, ids, ledger


def create(
    conn: sqlite3.Connection,
    *,
    description: str,
    spec_brief_id: str,
    sponsor: str,
    holder_brief_id: str,
    subject_url_text: str,
    checker_id: str,
    attached: bool,
    actor: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    """A new task held by *holder_brief_id*; a different *spec_brief_id* observes it."""
    if not description.strip() or "\n" in description:
        raise ValueError("a task description is one nonempty line")

    new_id = str(uuid.uuid4())
    event_id, state = ledger.create(
        conn,
        new_id,
        {
            "description": description.strip(),
            "spec_brief_id": spec_brief_id,
            "sponsor": sponsor,
            "holder": f"brief:{holder_brief_id}",
            "subject_url": ids.subject_url(subject_url_text),
            "checker_id": checker_id,
            "attached": attached,
        },
        actor,
        request_id,
        at,
    )
    associations.record_link(conn, holder_brief_id, new_id, "holder", event_id)
    if spec_brief_id != holder_brief_id:
        associations.record_link(conn, spec_brief_id, new_id, "observer", event_id)
    return {"task_id": new_id, "revision": state["revision"]}


def assign(
    conn: sqlite3.Connection,
    task: str,
    expected: int,
    to: str,
    reason: str,
    attached: bool,
    actor: str,
    request_id: str,
    at: float,
    *,
    check: bool = False,
) -> dict[str, ty.Any]:
    """Make *to* the holder now; the current holder becomes the previous one. With
    *check*, the task waits for *to* to check finished work, and *to* may close it.

    Anyone may assign a task. When *actor* isn't its holder, `taken_from` names the holder
    it was taken from, who should be told.
    """
    current = ledger.state(conn, task)
    if current is None:
        raise LookupError(f"no task:{task}")

    new_holder = ids.holder(to)
    ours = {f"brief:{n}" for n in identities.names(conn, actor)} | {new_holder}
    taken_from = "" if current["holder"] in ours else current["holder"]
    event_id, state = ledger.append(
        conn,
        task,
        expected,
        "assigned",
        {
            "holder": new_holder,
            "reason": reason,
            "attached": attached,
            "taken_from": taken_from,
            "check": check,
        },
        actor,
        request_id,
        at,
    )
    associations.record_link(conn, new_holder.removeprefix("brief:"), task, "holder", event_id)
    if current["holder"].startswith("brief:") and current["holder"] != new_holder:
        associations.handed_on(conn, current["holder"].removeprefix("brief:"), task)
    return {
        "task_id": task,
        "revision": state["revision"],
        "holder": new_holder,
        "previous_holder": state["previous_holder"],
        "taken_from": taken_from,
    }


def attach(conn: sqlite3.Connection, brief_id: str, actor: str, at: float) -> list[str]:
    """Record that *brief_id*'s lemon started, for each open assignment still waiting for
    it; returns their task IDs. Resuming an attached brief changes nothing. A lemon that
    started before an assignment counts as starting when it was assigned."""
    holders = [f"brief:{name}" for name in identities.names(conn, brief_id)]
    waiting = conn.execute(
        "SELECT task_id, revision, assigned_at FROM tasks"
        " WHERE lifecycle != 'closed' AND attached_at IS NULL"
        f" AND holder IN ({identities.placeholders(holders)})",
        holders,
    ).fetchall()
    for row in waiting:
        task, revision = row["task_id"], row["revision"]
        key = f"attach:{task}:{revision}"
        ledger.append(conn, task, revision, "attached", {}, actor, key, max(at, row["assigned_at"]))
    return [row["task_id"] for row in waiting]


def held_by(conn: sqlite3.Connection, brief_id: str) -> list[dict[str, ty.Any]]:
    """Open tasks *brief_id* holds."""
    names = identities.names(conn, brief_id)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM tasks WHERE lifecycle != 'closed'"
            f" AND holder IN ({identities.placeholders(names)}) ORDER BY created_at",
            [f"brief:{n}" for n in names],
        )
    ]
