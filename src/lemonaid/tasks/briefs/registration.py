"""Recording a planned task disposition once the new brief has its Lemon-ID.

The request ID comes from the brief, so a retry or `brief task ensure` after a crash
returns the first result instead of recording a second task.
"""

import sqlite3
import typing as ty

from ..model import associations, dependencies, holding, ledger
from . import planning


def _link(
    conn: sqlite3.Connection, planned: planning.Plan, brief_id: str, request_id: str, at: float
) -> dict[str, ty.Any]:
    state = ledger.state(conn, planned.task_id)
    assert state is not None
    actor = planned.actor or brief_id
    told = planned.attached and actor != brief_id
    if planned.mode == "observe":
        associations.observe(
            conn, planned.task_id, state["revision"], brief_id, actor, request_id, at
        )
        return {"disposition": "observe", "task_id": planned.task_id, "holder": state["holder"]}

    if (state["holder"], state["revision"]) != (
        planned.expected_holder,
        planned.expected_revision,
    ):
        raise ledger.Refused(
            f"task:{planned.task_id} changed since it was planned: now {state['holder']} at"
            f" revision {state['revision']}, planned from {planned.expected_holder} at"
            f" {planned.expected_revision}"
        )

    assigned = holding.assign(
        conn,
        planned.task_id,
        state["revision"],
        f"brief:{brief_id}",
        "brief created to take it",
        planned.attached,
        actor,
        request_id,
        at,
    )
    return {
        "disposition": "task",
        "task_id": planned.task_id,
        "taken_from": assigned["taken_from"],
        "tell_holder": told,
    }


def _record(
    conn: sqlite3.Connection,
    planned: planning.Plan,
    brief_id: str,
    sponsor: str,
    description: str,
    request_id: str,
    at: float,
) -> dict[str, ty.Any]:
    if planned.mode == "exempt":
        associations.exempt(conn, brief_id, planned.reason, "", at)
        return {"disposition": "exempt", "reason": planned.reason}

    if planned.mode != "new":
        return _link(conn, planned, brief_id, request_id, at)

    actor = planned.actor or sponsor or brief_id
    created = holding.create(
        conn,
        description=description,
        spec_brief_id=brief_id,
        sponsor=sponsor,
        holder_brief_id=brief_id,
        subject_url_text=planned.subject_url,
        checker_id="",
        attached=planned.attached,
        actor=actor,
        request_id=request_id,
        at=at,
    )
    if planned.parent_task_id:
        revision = ledger.state(conn, planned.parent_task_id)["revision"]
        dependencies.depend(
            conn,
            planned.parent_task_id,
            revision,
            created["task_id"],
            planned.actor or sponsor,
            request_id,
            at,
        )
    return {
        "disposition": "new",
        "task_id": created["task_id"],
        "parent_task_id": planned.parent_task_id,
        "tell_holder": planned.attached and actor != brief_id,
    }


def register(
    conn: sqlite3.Connection,
    planned: planning.Plan,
    brief_id: str,
    sponsor: str,
    description: str,
    at: float,
) -> dict[str, ty.Any]:
    request_id = f"register:{brief_id}"
    with ledger.transaction(conn):
        return ledger.once(
            conn,
            request_id,
            {"op": "register", "brief": brief_id, "sponsor": sponsor, **planned._asdict()},
            lambda: _record(conn, planned, brief_id, sponsor, description, request_id, at),
        )


def disposition(conn: sqlite3.Connection, brief_id: str) -> dict[str, ty.Any]:
    """The first task the brief held, its exemption, or a task it observes; empty when it
    has none of these."""
    if held := associations.held_of(conn, brief_id):
        return {"disposition": "holds", "task_id": held[0]}

    if reason := associations.exemption_of(conn, brief_id):
        return {"disposition": "exempt", "reason": reason}

    if observed := associations.observed_of(conn, brief_id):
        return {"disposition": "observe", "task_id": observed[0]}

    return {}


def ensure(
    conn: sqlite3.Connection,
    planned: planning.Plan,
    brief_id: str,
    sponsor: str,
    description: str,
    at: float,
) -> dict[str, ty.Any]:
    """The brief's disposition, registering *planned* if it has none yet."""
    if found := disposition(conn, brief_id):
        return {**found, "created": False}

    return {**register(conn, planned, brief_id, sponsor, description, at), "created": True}
