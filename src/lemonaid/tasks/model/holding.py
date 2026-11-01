"""Who holds a task: creating it with a holder, handing it on, its holder starting and
acknowledging it, and the open tasks a brief holds.

These run inside a caller's `ledger.transaction`. Brief IDs passed here are already
resolved to current Lemon-IDs; a holder is a tagged string (`brief:ID`, `human:ID` or
`external:ID`).
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
    delivery: str = "",
) -> dict[str, ty.Any]:
    """A new task held by *holder_brief_id*; a different *spec_brief_id* observes it.
    *delivery* is as for `assign`."""
    if not description.strip() or "\n" in description:
        raise ValueError("a task description is one nonempty line")

    new_id = str(uuid.uuid4())
    message_id = f"task-{new_id}-r1" if delivery == "message" else ""
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
            "delivery": delivery,
            "message_id": message_id,
        },
        actor,
        request_id,
        at,
    )
    associations.record_link(conn, holder_brief_id, new_id, "holder", event_id)
    if spec_brief_id != holder_brief_id:
        associations.record_link(conn, spec_brief_id, new_id, "observer", event_id)
    return {"task_id": new_id, "revision": state["revision"], "message_id": message_id}


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
    delivery: str = "",
    accountable: str = "",
    recheck_at: str = "",
    check: bool = False,
) -> dict[str, ty.Any]:
    """Make *to* the holder now; the current holder becomes the previous one. With
    *check*, the task waits for *to* to check finished work, and *to* may close it.

    Anyone may assign a task. When *actor* isn't its holder, `taken_from` names the holder
    it was taken from, who should be told. *delivery* is `message` when a running holder
    learns of the assignment from a queued message, named by the returned `message_id`,
    rather than from its launch context. A human holder needs the *accountable* brief that
    exposes the request; an external one also needs a *recheck_at* time.
    """
    current = ledger.state(conn, task)
    if current is None:
        raise LookupError(f"no task:{task}")

    new_holder = ids.holder(to)
    if not new_holder.startswith("brief:"):
        if not accountable:
            raise ValueError(f"{new_holder} needs an accountable brief")

        if new_holder.startswith("external:") and not recheck_at:
            raise ValueError(f"{new_holder} needs a recheck time")

    message_id = f"task-{task}-r{expected + 1}" if delivery == "message" else ""
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
            "delivery": delivery,
            "message_id": message_id,
            "accountable_brief_id": accountable,
            "recheck_at": recheck_at,
            "check": check,
        },
        actor,
        request_id,
        at,
    )
    if new_holder.startswith("brief:"):
        associations.record_link(conn, new_holder.removeprefix("brief:"), task, "holder", event_id)
    return {
        "task_id": task,
        "revision": state["revision"],
        "holder": new_holder,
        "previous_holder": state["previous_holder"],
        "taken_from": taken_from,
        "previous_accountable": current["accountable_brief_id"],
        "message_id": message_id,
    }


def attach(conn: sqlite3.Connection, brief_id: str, actor: str, at: float) -> list[str]:
    """Start the acknowledgment clock of each open assignment to *brief_id* still waiting
    for its lemon; returns their task IDs. Resuming an attached brief changes nothing."""
    holders = [f"brief:{name}" for name in identities.names(conn, brief_id)]
    waiting = [
        (row["task_id"], row["revision"])
        for row in conn.execute(
            "SELECT task_id, revision FROM tasks WHERE lifecycle != 'closed' AND attached_at IS NULL"
            f" AND holder IN ({identities.placeholders(holders)})",
            holders,
        )
    ]
    for task, revision in waiting:
        ledger.append(conn, task, revision, "attached", {}, actor, f"attach:{task}:{revision}", at)
    return [task for task, _ in waiting]


def acknowledge(
    conn: sqlite3.Connection, task: str, expected: int, actor: str, request_id: str, at: float
) -> dict[str, ty.Any]:
    """Accept the current assignment; acknowledging it again changes nothing."""
    current = ledger.state(conn, task)
    if current is None:
        raise LookupError(f"no task:{task}")

    if current["holder"] not in {f"brief:{n}" for n in identities.names(conn, actor)}:
        raise ValueError(f"task:{task} is held by {current['holder']}, not {actor}")

    if current["acknowledged_at"] is not None:
        return {"task_id": task, "revision": current["revision"], "acknowledged": "already"}

    _, state = ledger.append(
        conn,
        task,
        expected,
        "acknowledged",
        {"assignment_event_id": current["assignment_event_id"]},
        actor,
        request_id,
        at,
    )
    return {"task_id": task, "revision": state["revision"], "acknowledged": "now"}


def held_by(conn: sqlite3.Connection, brief_id: str) -> list[dict[str, ty.Any]]:
    """Open tasks *brief_id* holds, or answers for as the accountable brief of a human or
    external holder."""
    names = identities.names(conn, brief_id)
    marks = identities.placeholders(names)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM tasks WHERE lifecycle != 'closed'"
            f" AND (holder IN ({marks}) OR accountable_brief_id IN ({marks})) ORDER BY created_at",
            [*(f"brief:{n}" for n in names), *names],
        )
    ]
