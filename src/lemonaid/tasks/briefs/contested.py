"""Which briefs' Statuses an open challenge disputes, so the inbox can mark them contested.

A checker disputes a Status with a challenge whose obligation is `status-claim`, sent to the
brief whose Status it is. The mark lasts while the case is open: until the lemon changes its
Status or the facts change. lemonaid never changes the Status itself.
"""

import sqlite3

from ...brief import lemon

STATUS_CLAIM = "status-claim"


def by_lemon(conn: sqlite3.Connection) -> dict[str, str]:
    """Each contested brief's current Lemon-ID, with the oldest open challenge's text."""
    found: dict[str, str] = {}
    for row in conn.execute(
        "SELECT target, reason FROM task_cases WHERE resolved_at IS NULL AND kind = 'challenge'"
        " AND target_kind = 'brief' AND obligation = ? ORDER BY opened_at DESC, case_id DESC",
        (STATUS_CLAIM,),
    ):
        found[lemon.current(conn, row["target"]) or row["target"]] = row["reason"]
    return found
