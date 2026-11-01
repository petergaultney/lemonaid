"""What lemonaid tells lemons when a task changes hands, gains an observer, or closes.

Anyone may take, close or reopen a task, so the lemons it affects are told and can
coordinate if the change surprises them. A human or external holder is reached through
its accountable brief.
"""

import sqlite3
import typing as ty

from ...messages import store
from ..model import ledger

Task = ty.Mapping[str, ty.Any]


def observing(task_id: str, holder: str) -> str:
    return (
        f"linked to task:{task_id} as an observer; ownership is NOT transferred"
        f" (the holder is still {holder})"
    )


def tell(holder: str, accountable: str, body: str, sender: str, message_id: str = "") -> str:
    """Queue *body* for *holder*, or for the brief accountable for a human or external one;
    returns how that went, for the caller's output."""
    to = holder.removeprefix("brief:") if holder.startswith("brief:") else accountable
    if not to:
        return f"{holder} isn't a lemon; tell them yourself"

    try:
        store.send(store.inbox_for_id(to), body, sender or "lemonaid", message_id)
    except (ValueError, OSError) as error:
        return f"telling {to} failed: {error}"

    return f"{to} has been told"


def _reach(holder: str) -> str:
    return (
        f": `lemonaid tell {holder.removeprefix('brief:')}`" if holder.startswith("brief:") else "."
    )


def tell_taken(task: Task, taken_from: str, accountable: str, new_holder: str, actor: str) -> str:
    by = f", assigned by {actor}" if actor and f"brief:{actor}" != new_holder else ""
    body = (
        f"task:{task['task_id']} ({task['description']}) was taken from"
        f" {'you' if taken_from.startswith('brief:') else f'{taken_from}, which you answer for'}."
        f" {new_holder} holds it now{by}. If that surprises you, coordinate with them"
        f"{_reach(new_holder)}"
    )
    return f"task:{task['task_id']} was taken from {taken_from}; " + tell(
        taken_from, accountable, body, actor
    )


def tell_holder(task: Task, actor: str, reason: str, message_id: str) -> str:
    """Tell a running brief it was just assigned *task*; *message_id* lets the inspector
    see when the message was read."""
    body = (
        f"You now hold task:{task['task_id']} ({task['description']}), assigned by"
        f" {actor or 'lemonaid'}: {reason}. Once you have read it and accept it, run"
        f" `lemonaid task acknowledge {task['task_id']}`."
    )
    return tell(task["holder"], "", body, actor, message_id)


def tell_closed(task: Task, actor: str, reason: str) -> str:
    """Tell the holder its task was closed or reopened by someone else."""
    body = (
        f"task:{task['task_id']} ({task['description']}) is now {task['lifecycle']},"
        f" by {actor or 'lemonaid'}: {reason}."
    )
    return tell(task["holder"], task["accountable_brief_id"], body, actor)


def tell_released(parent: Task, child: Task, actor: str, reason: str) -> str:
    """Tell a waiting task's holder that the task it waited for closed."""
    body = (
        f"task:{child['task_id']} ({child['description']}), which your task:{parent['task_id']}"
        f" waits for, was closed: {reason}. Pick up its result and carry on."
    )
    return tell(parent["holder"], parent["accountable_brief_id"], body, actor)


def notice(conn: sqlite3.Connection, result: ty.Mapping[str, ty.Any], actor: str) -> str:
    """The line to show for a recorded disposition or assignment, after telling the former
    holder of a taken task; "" when the task neither was taken nor gained an observer."""
    if result.get("disposition") == "observe" and result.get("holder"):
        return observing(result["task_id"], result["holder"])

    if taken := result.get("taken_from"):
        task = ledger.state(conn, result["task_id"])
        assert task is not None
        return tell_taken(
            task, taken, result.get("previous_accountable", ""), task["holder"], actor
        )

    return ""
