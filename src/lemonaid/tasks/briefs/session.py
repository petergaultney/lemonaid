"""What a lemon learns about its tasks when its session starts.

The first attachment to a brief starts the acknowledgment clock of each assignment waiting
for it; a resumed session finds those clocks already running.
"""

import sqlite3
import time
from pathlib import Path

from ...brief import identity
from ..model import holding, identities, ledger


def _line(task: dict) -> str:
    acknowledged = task["acknowledged_at"] is not None
    return f"- task:{task['task_id']} ({task['description']})" + (
        ""
        if acknowledged
        else f", not yet acknowledged: `lemonaid task acknowledge {task['task_id']}`"
    )


def started(conn: sqlite3.Connection, path: Path, at: float) -> str:
    """Start waiting assignments' clocks and describe the brief's open tasks; "" if it has none."""
    try:
        lemon_id = identities.current(conn, identity.read(path.read_text()))
    except (OSError, ValueError):
        return ""

    if not lemon_id:
        return ""

    with ledger.transaction(conn):
        holding.attach(conn, lemon_id, lemon_id, at)
    held = holding.held_by(conn, lemon_id)
    if not held:
        return ""

    return "\n".join(
        [
            "Your brief holds these open tasks. Acknowledge an assignment once you have read it"
            " and accept it; running the hook did not acknowledge anything.",
            *(_line(t) for t in held),
        ]
    )


def context(conn: sqlite3.Connection, path: Path, enabled: bool) -> str:
    return started(conn, path, time.time()) if enabled else ""
