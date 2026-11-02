"""Planning a new brief's task disposition, before its file exists.

A plan pins what it saw: taking a task records the holder and revision it was planned
against, and a new task records the parent task it blocks. `repair_flags` gives the
options that make `brief task ensure` register the same plan rather than a default one.
"""

import shlex
import sqlite3
import typing as ty

from ..model import holding, identities, ledger

MODES = ("new", "task", "observe", "exempt")


class Plan(ty.NamedTuple):
    mode: str
    task_id: str = ""
    reason: str = ""
    parent_task_id: str = ""
    actor: str = ""
    expected_holder: str = ""
    expected_revision: int = 0
    attached: bool = False
    subject_url: str = ""  # a new task's URL


def _held_directly(conn: sqlite3.Connection, brief_id: str) -> list[str]:
    holders = {f"brief:{name}" for name in identities.names(conn, brief_id)}
    return [t["task_id"] for t in holding.held_by(conn, brief_id) if t["holder"] in holders]


def _parent_task(conn: sqlite3.Connection, sponsor: str, for_task: str, independent: bool) -> str:
    """The sponsor's task the new brief's work blocks, if any."""
    if for_task:
        if ledger.state(conn, for_task) is None:
            raise ledger.Refused(f"--for-task: no task:{for_task}")

        return for_task

    if independent or not sponsor:
        return ""

    held = _held_directly(conn, sponsor)
    if len(held) > 1:
        raise ledger.Refused(
            f"{sponsor} holds {len(held)} open tasks; pass --for-task TASK_ID or --independent"
        )

    return held[0] if held else ""


def plan(
    conn: sqlite3.Connection,
    mode: str,
    task_id: str,
    reason: str,
    sponsor: str,
    actor: str,
    for_task: str,
    independent: bool,
    attached: bool,
) -> Plan:
    """Raises ledger.Refused for a combination that can't be registered."""
    if mode not in MODES:
        raise ledger.Refused(f"unknown task mode {mode!r}")

    if mode == "exempt":
        if not reason.strip():
            raise ledger.Refused("--no-task needs a reason")

        return Plan(mode, reason=reason.strip(), actor=actor)

    if mode != "new":
        state = ledger.state(conn, task_id)
        if state is None:
            raise ledger.Refused(f"--task: no task:{task_id}")

        return Plan(
            mode,
            task_id=task_id,
            actor=actor,
            expected_holder=state["holder"],
            expected_revision=state["revision"],
            attached=attached,
        )

    return Plan(
        mode,
        parent_task_id=_parent_task(conn, sponsor, for_task, independent),
        actor=actor,
        attached=attached,
    )


def repair_flags(planned: Plan) -> str:
    """`brief task ensure` options that register *planned* again."""
    match planned.mode:
        case "exempt":
            return f"--no-task {shlex.quote(planned.reason)}"
        case "new":
            url = f" --task-url {shlex.quote(planned.subject_url)}" if planned.subject_url else ""
            parent = (
                f"--for-task {planned.parent_task_id}"
                if planned.parent_task_id
                else "--independent"
            )
            return parent + url
        case "observe":
            return f"--task {planned.task_id} --observe"
    return f"--task {planned.task_id}"
