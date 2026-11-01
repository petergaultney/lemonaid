"""Marking a brief done while it holds tasks: its parent checks the work.

A lemon with a parent doesn't close a task it holds. Setting its brief done hands each
task it holds to the parent in the `check` state, in which its new holder may close it,
ask a human, or hand it back. A task held by a human or external party that the brief
answers for stays with that holder, and the parent answers for it instead, also in
`check`. A lemon with no parent (usually the control center) closes its own tasks.
"""

import sqlite3
import time
import typing as ty
from collections import abc
from pathlib import Path

from ...brief import identity
from ...lineage import links
from ..model import holding, identities, ledger
from . import notices

Task = ty.Mapping[str, ty.Any]


def open_tasks(conn: sqlite3.Connection, path: Path) -> tuple[str, list[dict[str, ty.Any]]]:
    """The Lemon-ID of the brief at *path* and the open tasks it holds or answers for;
    ("", []) if it has no Lemon-ID."""
    try:
        lemon_id = identities.current(conn, identity.read(path.read_text()))
    except (OSError, ValueError):
        return "", []

    return lemon_id, holding.held_by(conn, lemon_id) if lemon_id else []


def checker(conn: sqlite3.Connection, holder_id: str) -> str:
    """Who checks *holder_id*'s finished tasks: its parent, or "" when it has none."""
    return links.parent_of(conn, holder_id)


def _tell_checker(task: Task, holder_id: str) -> str:
    task_id = task["task_id"]
    held = (
        f"{task['holder']} holds it, and you now answer for it instead of {holder_id}. Check"
        f" that it's done, then close it with `lemonaid task close {task_id} --reason TEXT`"
        if task["accountable_brief_id"]
        else "you hold it now to check. Check the work, then close it with"
        f" `lemonaid task close {task_id} --reason TEXT`, ask a human with"
        f" `lemonaid task assign {task_id} --to human:NAME --accountable self --reason TEXT`,"
    )
    body = (
        f"{holder_id} says task:{task_id} ({task['description']}) is done, so {held}"
        f" or hand it back with `lemonaid task assign {task_id} --to {holder_id} --reason TEXT`."
    )
    return notices.tell(task["holder"], task["accountable_brief_id"], body, holder_id)


def _hand(
    conn: sqlite3.Connection, task: Task, holder_id: str, to: str, running: bool
) -> dict[str, ty.Any]:
    """Hand *task* to *to*; one held by a human or external party stays with that holder,
    and *to* answers for it instead."""
    request_id = f"done-{task['task_id']}-r{task['revision']}"
    lemon_held = task["holder"].startswith("brief:")
    with ledger.transaction(conn):
        return ledger.once(
            conn,
            request_id,
            {"op": "done", "task_id": task["task_id"], "to": to},
            lambda: holding.assign(
                conn,
                task["task_id"],
                task["revision"],
                f"brief:{to}" if lemon_held else task["holder"],
                "says this is done; check the work",
                running,
                holder_id,
                request_id,
                time.time(),
                accountable="" if lemon_held else to,
                recheck_at="" if lemon_held else task["recheck_at"],
                check=True,
            ),
        )


def hand_to_parent(
    conn: sqlite3.Connection,
    holder_id: str,
    tasks: abc.Iterable[Task],
    running: abc.Callable[[str], bool],
) -> tuple[list[str], list[Task]]:
    """Hand each of *tasks* that *holder_id* holds or answers for to its parent; returns a
    line per handoff and the tasks that still keep the brief from being done. *running*
    says whether a brief's lemon is running now."""
    parent = checker(conn, holder_id)
    names = identities.names(conn, holder_id)
    mine = {f"brief:{name}" for name in names}
    said: list[str] = []
    kept: list[Task] = []
    for task in tasks:
        if not parent or not (task["holder"] in mine or task["accountable_brief_id"] in names):
            kept.append(task)
            continue

        awake = running(parent)
        _hand(conn, task, holder_id, parent, awake)
        state = ledger.state(conn, task["task_id"])
        assert state is not None
        told = _tell_checker(state, holder_id) if awake else ""
        said.append(f"task:{task['task_id']} handed to {parent} to check. {told}".strip())
    return said, kept


def hand_on_archive(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """Hand each open task *lemon_id* holds to its parent, or else to the task's previous
    holder or sponsor, before its brief is archived; returns a line per handoff. Raises
    ValueError when a task has no one to go to, so the archive doesn't orphan it."""
    mine = {f"brief:{name}" for name in identities.names(conn, lemon_id)}
    said = []
    for task in holding.held_by(conn, lemon_id):
        if task["holder"] not in mine:
            continue

        to = next(
            (
                who
                for who in (
                    checker(conn, lemon_id),
                    task["previous_holder"].removeprefix("brief:"),
                    task["sponsor"],
                )
                if who
                and f"brief:{who}" not in mine
                and not who.startswith(("human:", "external:"))
            ),
            "",
        )
        if not to:
            raise ValueError(
                f"task:{task['task_id']} has no one to go to; close it or hand it on first"
            )

        with ledger.transaction(conn):
            holding.assign(
                conn,
                task["task_id"],
                task["revision"],
                f"brief:{to}",
                "its holder's brief was archived",
                notices.running(conn, to),
                lemon_id,
                f"archive-{task['task_id']}-r{task['revision']}",
                time.time(),
            )
        state = ledger.state(conn, task["task_id"])
        assert state is not None
        told = notices.tell_holder(state, lemon_id, "its holder's brief was archived")
        said.append(f"task:{task['task_id']} handed to {to}. {told}".strip())
    return said


def refusal(held: abc.Iterable[Task]) -> str:
    return "\n".join(
        [
            "Refused: this brief still holds open tasks. Close each one, or give it to its next"
            " holder, then mark the brief done:",
            *(
                f"- task:{t['task_id']} ({t['description']}):"
                f" `lemonaid task close {t['task_id']} --reason ...` or"
                f" `lemonaid task assign {t['task_id']} --to BRIEF --reason ...`"
                for t in held
            ),
        ]
    )
