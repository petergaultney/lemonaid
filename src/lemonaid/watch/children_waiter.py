"""Whether a parent is watching its children, and the words that tell it to.

Any running children waiter for the parent counts, whatever its options.
"""

import os
import sqlite3

from ..brief import lemon
from ..lineage import links
from . import registry

COMMAND = "lemonaid watch briefs --children --self --once"

CLAUDE_REMINDER = (
    f"Watch your children: run `{COMMAND}` as a background Bash task (run_in_background) "
    "and list it under `## Waiters` in your brief; rearm it after each wake."
)

CODEX_REMINDER = (
    "Watch your children: run `lemonaid watch briefs --children --self --codex-thread` as an "
    "escalated `exec_command` session and list it under `## Waiters` in your brief; "
    "each event is queued into your thread, so rearm it after each one."
)


def reminder() -> str:
    """The reminder for the calling harness: Codex when its thread ID is in the environment."""
    return CODEX_REMINDER if os.environ.get("CODEX_THREAD_ID") else CLAUDE_REMINDER


def with_briefs(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """Lemon-IDs of *lemon_id*'s children that have a brief to watch."""
    return [
        child
        for child in links.children_of(conn, lemon_id)
        if (path := lemon.brief_of(conn, child)) and path.is_file()
    ]


def is_armed(lemon_id: str) -> bool:
    """Whether any `watch briefs --children` waiter (including `--orphans` or `--to`) runs for *lemon_id*."""
    return bool(registry.running_for("briefs", lemon_id))
