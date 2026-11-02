"""Marking a brief done while it holds tasks: its parent checks the work.

A lemon with a parent doesn't close a task it holds. Setting its brief done hands each
task it holds to the nearest live lemon from its parent up, in the `check` state, in which
its new holder may close it or hand it back. A lemon with no parent (usually the control
center) closes its own tasks.
"""

import sqlite3
import time
import typing as ty
from collections import abc
from pathlib import Path

from ...brief import identity
from ...lineage import links
from ..model import holding, identities, ledger
from . import liveness, notices

Task = ty.Mapping[str, ty.Any]


def open_tasks(conn: sqlite3.Connection, path: Path) -> tuple[str, list[dict[str, ty.Any]]]:
    """The Lemon-ID of the brief at *path* and the open tasks it holds; ("", []) if it has
    no Lemon-ID."""
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
    body = (
        f"{holder_id} says task:{task_id} ({task['description']}) is done, so you hold it"
        f" now to check. Check the work, then close it with"
        f" `lemonaid task close {task_id} --reason TEXT`, or hand it back with"
        f" `lemonaid task assign {task_id} --to {holder_id} --reason TEXT`."
    )
    return notices.tell(task["holder"], body, holder_id)


def _hand(conn: sqlite3.Connection, task: Task, holder_id: str, to: str) -> dict[str, ty.Any]:
    request_id = f"done-{task['task_id']}-r{task['revision']}"
    with ledger.transaction(conn):
        return ledger.once(
            conn,
            request_id,
            {"op": "done", "task_id": task["task_id"], "to": to},
            lambda: holding.assign(
                conn,
                task["task_id"],
                task["revision"],
                f"brief:{to}",
                "says this is done; check the work",
                True,
                holder_id,
                request_id,
                time.time(),
                check=True,
            ),
        )


def hand_to_parent(
    conn: sqlite3.Connection, holder_id: str, tasks: abc.Iterable[Task]
) -> tuple[list[str], list[Task], str]:
    """Hand each of *tasks* that *holder_id* holds to the nearest live lemon from its
    parent up; returns a line per handoff, the tasks that still keep the brief from being
    done, and why when its parent has no live lemon above it."""
    parent = checker(conn, holder_id)
    to = liveness.nearest(conn, parent) if parent else ""
    mine = {f"brief:{name}" for name in identities.names(conn, holder_id)}
    said: list[str] = []
    kept: list[Task] = []
    for task in tasks:
        if not to or task["holder"] not in mine:
            kept.append(task)
            continue

        _hand(conn, task, holder_id, to)
        state = ledger.state(conn, task["task_id"])
        assert state is not None
        told = _tell_checker(state, holder_id)
        said.append(f"task:{task['task_id']} handed to {to} to check. {told}".strip())
    return said, kept, liveness.refusal(parent) if parent and not to else ""


def hand_on_archive(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """Hand each open task *lemon_id* holds to the nearest live lemon from its parent up,
    or else to the task's previous holder or sponsor while live, before its brief is
    archived; returns a line per handoff. Raises ValueError when a task has no live lemon to
    go to, so the archive doesn't orphan it."""
    mine = {f"brief:{name}" for name in identities.names(conn, lemon_id)}
    up = liveness.nearest(conn, checker(conn, lemon_id))
    said = []
    for task in holding.held_by(conn, lemon_id):
        to = up or next(
            (
                who
                for who in (task["previous_holder"].removeprefix("brief:"), task["sponsor"])
                if who and f"brief:{who}" not in mine and liveness.live(conn, who)
            ),
            "",
        )
        if not to:
            raise ValueError(
                f"task:{task['task_id']} has no live lemon to go to; resume one, or close it or"
                " hand it on first"
            )

        with ledger.transaction(conn):
            holding.assign(
                conn,
                task["task_id"],
                task["revision"],
                f"brief:{to}",
                "its holder's brief was archived",
                True,
                lemon_id,
                f"archive-{task['task_id']}-r{task['revision']}",
                time.time(),
            )
        state = ledger.state(conn, task["task_id"])
        assert state is not None
        told = notices.tell_holder(state, lemon_id, "its holder's brief was archived")
        said.append(f"task:{task['task_id']} handed to {to}. {told}".strip())
    return said


def refusal(held: abc.Iterable[Task], why: str = "") -> str:
    return "\n".join(
        [
            *([f"{why}."] if why else []),
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
