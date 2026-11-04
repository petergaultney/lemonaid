"""Checker input for live tasks: each open task's fields, flattened, plus the facts about
its holder, its PR and the tasks it waits for.

The result is a `corpus.Snapshot`, so live evaluation and offline replay feed a checker the
same records.
"""

import sqlite3
import typing as ty
from collections import abc

from ...lineage import links
from ..checker import corpus
from ..model import dependencies
from . import cases, live


def _when(at: float | None) -> str:
    return live.stamp(at) if at is not None else ""


def released(
    conn: sqlite3.Connection, state: ty.Mapping[str, ty.Any], now: float, grace: float
) -> dict[str, str]:
    """The tasks *state* waited for that closed during its current assignment less than
    *grace* seconds ago, each with when it closed."""
    return {
        row["child_task_id"]: live.stamp(row["at"])
        for row in conn.execute(
            "SELECT d.child_task_id, e.at FROM task_dependencies d"
            " JOIN task_events e ON e.event_id = d.resolved_event_id"
            " WHERE d.parent_task_id = ? AND d.resolved_event_id > ?",
            (state["task_id"], state["assignment_event_id"]),
        )
        if row["at"] + grace > now
    }


def _closing(conn: sqlite3.Connection, state: ty.Mapping[str, ty.Any]) -> dict[str, str]:
    """Who closed *state* and when, and `closed.carried_by`, the unclosed tasks with its URL."""
    row = conn.execute(
        "SELECT actor, at FROM task_events WHERE task_id = ? AND kind = 'closed'"
        " ORDER BY revision DESC LIMIT 1",
        (state["task_id"],),
    ).fetchone()
    carriers = conn.execute(
        "SELECT task_id FROM tasks WHERE subject_url = ? AND subject_url != ''"
        " AND lifecycle != 'closed' ORDER BY task_id",
        (state["subject_url"],),
    )
    return {
        **({"closed.by": row["actor"], "closed.at": _when(row["at"])} if row else {}),
        "closed.carried_by": ",".join(r["task_id"] for r in carriers),
    }


def _recheck(conn: sqlite3.Connection, task_id: str) -> dict[str, str]:
    """When a re-check of the holder's Status was last requested, and that request's event."""
    row = conn.execute(
        "SELECT event_id, at FROM task_events WHERE task_id = ? AND kind = 'recheck_requested'"
        " ORDER BY revision DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    return (
        {"recheck.requested_at": _when(row["at"]), "recheck.event": str(row["event_id"])}
        if row
        else {}
    )


def fields(
    conn: sqlite3.Connection,
    state: ty.Mapping[str, ty.Any],
    releases: ty.Mapping[str, str],
) -> dict[str, str]:
    """*state* as the checker's flat string fields; *releases* are from `released`."""
    return {
        "task_id": state["task_id"],
        "description": state["description"],
        "lifecycle": state["lifecycle"],
        "holder": state["holder"],
        "previous_holder": state["previous_holder"],
        "revision": str(state["revision"]),
        "sponsor": state["sponsor"],
        "spec_brief_id": state["spec_brief_id"],
        "subject_url": state["subject_url"],
        "holder_parent": links.parent_of(conn, state["holder"].removeprefix("brief:")),
        "assignment.transfer_event": str(state["assignment_event_id"]),
        "assignment.by": conn.execute(
            "SELECT actor FROM task_events WHERE event_id = ?", (state["assignment_event_id"],)
        ).fetchone()["actor"],
        "assignment.assigned_at": _when(state["assigned_at"]),
        "assignment.attached_at": _when(state["attached_at"]),
        **{
            f"dependency.{child}": "open"
            for child in dependencies.waits_for(conn, state["task_id"])
        },
        **{f"dependency.{child}": "released" for child in releases},
        **_recheck(conn, state["task_id"]),
        **(_closing(conn, state) if state["lifecycle"] == "closed" else {}),
    }


def dependency_facts(
    task_id: str, releases: ty.Mapping[str, str], loop: abc.Sequence[str], now: float
) -> list[live.Fact]:
    """What only lemonaid knows about *task_id*'s dependencies: when each of *releases*
    closed, and `cycle`, the tasks in a dependency *loop* through it ("" for
    none). A dependency's own lifecycle and finding come from the checker's task watches."""
    return [
        *(live.fact("task", child, "released_at", at, now) for child, at in releases.items()),
        live.fact(
            "task", task_id, "cycle", ",".join(sorted({task_id, *loop}) if loop else []), now
        ),
    ]


def case_records(conn: sqlite3.Connection, subject: str) -> list[dict[str, str]]:
    """The open cases of *subject* (`task:ID` or `brief:ID`), as checker case records."""
    return [
        {
            "case_id": str(c["case_id"]),
            "task_id": subject.partition(":")[2],
            "obligation": c["obligation"],
            "evidence": c["evidence"],
            "kind": c["kind"],
            "target": f"{c['target_kind']}:{c['target']}",
            "reason": c["reason"],
            "opened_at": live.stamp(c["opened_at"]),
            "notified_at": _when(c["notified_at"]),
        }
        for c in cases.open_cases(conn)
        if c["subject"] == subject
    ]


def snapshot(
    now: float,
    context: ty.Mapping[str, str],
    task: dict[str, str],
    facts: abc.Iterable[live.Fact],
    open_cases: abc.Sequence[dict[str, str]],
) -> corpus.Snapshot:
    """One task's input: a checker may need facts no other task does."""
    unique = {(f["kind"], f["key"], f["field"]): f for f in facts}
    return corpus.Snapshot(
        name="live",
        now=live.stamp(now),
        context=dict(context),
        tasks=[task],
        cases=list(open_cases),
        facts=list(unique.values()),
        expected={},
    )
