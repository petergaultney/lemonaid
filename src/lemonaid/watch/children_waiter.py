"""Whether a parent is watching its children, and the words that tell it to.

The check only knows the default waiter (`--to` unset, no `--me`); a parent that arms
another one is reminded until it arms the default too.
"""

import os
import pathlib
import sqlite3

from ..brief import lemon
from ..lineage import links
from . import briefs_cli, briefs_events, waiter_lock

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


def is_armed(lemon_id: str, state_dir: pathlib.Path | None = None) -> bool:
    stem = briefs_events.state_stem(
        state_dir or briefs_events.default_state_dir(),
        lemon_id,
        "",
        frozenset(briefs_cli.CHILD_TO),
        False,
    )
    return waiter_lock.held(stem.with_suffix(".lock"))
