"""What lemonaid says when a task changes hands or gains an observer.

A task taken by someone other than its holder is still taken; the former holder is told,
so it can coordinate with the new holder if the move surprises it.
"""

import sqlite3
import typing as ty

from ...messages import store
from ..model import ledger


def observing(task_id: str, holder: str) -> str:
    return (
        f"linked to task:{task_id} as an observer; ownership is NOT transferred"
        f" (the holder is still {holder})"
    )


def _taken(task: ty.Mapping[str, ty.Any], new_holder: str, actor: str) -> str:
    by = f", assigned by {actor}" if actor and f"brief:{actor}" != new_holder else ""
    reach = (
        f": `lemonaid tell {new_holder.removeprefix('brief:')}`"
        if new_holder.startswith("brief:")
        else "."
    )
    return (
        f"task:{task['task_id']} ({task['description']}) was taken from you."
        f" {new_holder} holds it now{by}. If that surprises you, coordinate with them{reach}"
    )


def tell_taken(task: ty.Mapping[str, ty.Any], taken_from: str, new_holder: str, actor: str) -> str:
    """Queue a message for the brief *task* was taken from; returns a line for the caller."""
    if not taken_from.startswith("brief:"):
        return f"task:{task['task_id']} was taken from {taken_from}; tell them yourself"

    former = taken_from.removeprefix("brief:")
    try:
        store.send(store.inbox_for_id(former), _taken(task, new_holder, actor), actor or "lemonaid")
    except (ValueError, OSError) as error:
        return f"task:{task['task_id']} was taken from {former}, but telling it failed: {error}"

    return f"task:{task['task_id']} was taken from {former}; it has been told"


def tell_holder(task: ty.Mapping[str, ty.Any], new_holder: str, actor: str, reason: str) -> str:
    """Queue a message for a running brief a task was just assigned to; returns a line."""
    to = new_holder.removeprefix("brief:")
    body = (
        f"You now hold task:{task['task_id']} ({task['description']}), assigned by"
        f" {actor or 'lemonaid'}: {reason}. Once you have read it and accept it, run"
        f" `lemonaid task acknowledge {task['task_id']}`."
    )
    try:
        store.send(store.inbox_for_id(to), body, actor or "lemonaid")
    except (ValueError, OSError) as error:
        return f"telling {to} about task:{task['task_id']} failed: {error}"

    return f"{to} has been told it holds task:{task['task_id']}"


def notice(
    conn: sqlite3.Connection, result: ty.Mapping[str, ty.Any], new_holder: str, actor: str
) -> str:
    """The line to show for a recorded disposition or assignment, after telling the former
    holder of a taken task; "" when the task neither was taken nor gained an observer."""
    if result.get("disposition") == "observe" and result.get("holder"):
        return observing(result["task_id"], result["holder"])

    if taken := result.get("taken_from"):
        return tell_taken(ledger.state(conn, result["task_id"]), taken, new_holder, actor)

    return ""
