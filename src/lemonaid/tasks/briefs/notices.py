"""What lemonaid tells lemons when a task changes hands, gains an observer, or closes.

Anyone may take, close or reopen a task, so the lemons it affects are told and can
coordinate if the change surprises them.
"""

import sqlite3
import typing as ty

from ... import brief
from ...messages import store
from ..model import ledger

Task = ty.Mapping[str, ty.Any]


def running(conn: sqlite3.Connection, brief_id: str) -> bool:
    """Whether a lemon has *brief_id*'s brief now, not a window still waiting for one; a
    running holder is told of a task by message, and one yet to start by its launch context."""
    path = brief.lemon.brief_of(conn, brief_id)
    return any(a.channel for a in brief.attached.for_paths(conn, [path])) if path else False


def observing(task_id: str, holder: str) -> str:
    return (
        f"linked to task:{task_id} as an observer; ownership is NOT transferred"
        f" (the holder is still {holder})"
    )


def tell(holder: str, body: str, sender: str) -> str:
    """Queue *body* for *holder*; returns how that went, for the caller's output."""
    to = holder.removeprefix("brief:")

    try:
        store.send(store.mailbox_for_id(to), body, sender or "lemonaid")
    except (ValueError, OSError) as error:
        return f"telling {to} failed: {error}"

    return f"{to} has been told"


def tell_taken(task: Task, taken_from: str, new_holder: str, actor: str) -> str:
    by = f", assigned by {actor}" if actor and f"brief:{actor}" != new_holder else ""
    body = (
        f"task:{task['task_id']} ({task['description']}) was taken from you."
        f" {new_holder} holds it now{by}. If that surprises you, coordinate with them:"
        f" `lemonaid tell {new_holder.removeprefix('brief:')}`"
    )
    return f"task:{task['task_id']} was taken from {taken_from}; " + tell(taken_from, body, actor)


def tell_holder(task: Task, actor: str, reason: str) -> str:
    """Tell a running brief it was just assigned *task*."""
    body = (
        f"You now hold task:{task['task_id']} ({task['description']}), assigned by"
        f" {actor or 'lemonaid'}: {reason}. When you are no longer the one to move next on it,"
        f" hand it to the lemon that must act on your result (not your parent unless it does)"
        f" with `lemonaid task assign {task['task_id']} --to BRIEF --reason TEXT`. When the work"
        f" is finished, close it with `lemonaid task close {task['task_id']} --reason TEXT`,"
        " naming where the result is."
    )
    return tell(task["holder"], body, actor)


def tell_closed(task: Task, actor: str, reason: str) -> str:
    """Tell the holder its task was closed or reopened by someone else."""
    body = (
        f"task:{task['task_id']} ({task['description']}) is now {task['lifecycle']},"
        f" by {actor or 'lemonaid'}: {reason}."
    )
    return tell(task["holder"], body, actor)


def tell_released(parent: Task, child: Task, actor: str, reason: str) -> str:
    """Tell a waiting task's holder that the task it waited for closed."""
    body = (
        f"task:{child['task_id']} ({child['description']}), which your task:{parent['task_id']}"
        f" waits for, was closed: {reason}. Pick up its result and carry on."
    )
    return tell(parent["holder"], body, actor)


def notice(
    conn: sqlite3.Connection,
    result: ty.Mapping[str, ty.Any],
    actor: str,
    reason: str = "your brief's task",
) -> str:
    """The lines to show for a recorded disposition or assignment, after telling the former
    holder of a taken task, and the new holder when *result* says `tell_holder`; "" when
    none of these happened."""
    if result.get("disposition") == "observe" and result.get("holder"):
        return observing(result["task_id"], result["holder"])

    task = ledger.state(conn, result["task_id"]) if result.get("task_id") else None
    if task is None:
        return ""

    taken = result.get("taken_from")
    return "\n".join(
        [
            *([tell_taken(task, taken, task["holder"], actor)] if taken else []),
            *([tell_holder(task, actor, reason)] if result.get("tell_holder") else []),
        ]
    )
