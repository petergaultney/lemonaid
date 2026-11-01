"""What a lemon learns about its tasks when its session starts.

The first attachment to a brief records that its lemon started, for each assignment
waiting for it.
"""

import sqlite3
import time
from pathlib import Path

from ...brief import identity
from ..model import holding, identities, ledger


def started(conn: sqlite3.Connection, path: Path, at: float) -> str:
    """Record the start for waiting assignments and describe the brief's open tasks; "" if
    it has none."""
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
            "Your brief holds these open tasks. When you are no longer the one to move next on"
            " one, hand it on with `lemonaid task assign TASK_ID --to BRIEF --reason TEXT`.",
            *(f"- task:{t['task_id']} ({t['description']})" for t in held),
        ]
    )


def context(conn: sqlite3.Connection, path: Path, enabled: bool) -> str:
    return started(conn, path, time.time()) if enabled else ""
