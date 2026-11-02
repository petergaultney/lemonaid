"""What a lemon learns about its tasks when its session starts.

The first attachment to a brief records that its lemon started, for each assignment
waiting for it. A brief attached after its session started, as `lemon start --brief`
does, is caught up by the inspector's next pass.
"""

import sqlite3
import time
from pathlib import Path

from ... import brief
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


def caught_up(conn: sqlite3.Connection) -> list[str]:
    """Record the start, at its brief's attachment time, of each lemon now attached whose
    assignments are still waiting for it; returns those task IDs."""
    holders = {
        row["holder"].removeprefix("brief:")
        for row in conn.execute(
            "SELECT DISTINCT holder FROM tasks WHERE lifecycle != 'closed' AND attached_at IS NULL"
        )
    }
    started = {}
    for lemon_id in holders:
        try:
            found = brief.lemon.attachment(conn, lemon_id)
        except LookupError:
            continue

        if found.channel:
            started[lemon_id] = found.attached_at
    with ledger.transaction(conn):
        return [
            t
            for lemon_id, at in started.items()
            for t in holding.attach(conn, lemon_id, lemon_id, at)
        ]


def context(conn: sqlite3.Connection, path: Path, enabled: bool) -> str:
    return started(conn, path, time.time()) if enabled else ""
