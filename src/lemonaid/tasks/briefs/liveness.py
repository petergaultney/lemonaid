"""Whether a brief's lemon is live, and the nearest live lemon up a brief's lineage.

A task is only handed to a live lemon: one attached to its brief whose harness runs. A
dead harness, an archived brief, or a brief with no lemon attached is not live.
"""

import sqlite3

from ... import brief
from ...lineage import links
from ...messages import recipient, store


def live(conn: sqlite3.Connection, lemon_id: str) -> bool:
    try:
        found = brief.lemon.attachment(conn, lemon_id)
    except LookupError:
        return False

    if not found.channel:
        return False

    state = recipient.probe(found.channel, found.notification, store.inbox_for_id(lemon_id))
    return state.state not in (recipient.DEAD, recipient.NOT_STARTED)


def nearest(conn: sqlite3.Connection, lemon_id: str) -> str:
    """*lemon_id* if it is live, else its nearest live ancestor; "" when none is."""
    seen = set()
    while lemon_id and lemon_id not in seen:
        if live(conn, lemon_id):
            return lemon_id

        seen.add(lemon_id)
        lemon_id = links.parent_of(conn, lemon_id)
    return ""


def refusal(lemon_id: str) -> str:
    return (
        f"{lemon_id} isn't live, and a task is only handed to a live lemon: resume it with"
        f" `lemonaid lemon resume {lemon_id}`, or hand the task to a live lemon"
    )
