"""The missing role waiters of one lemon, as the words that tell it what to arm."""

import sqlite3
from collections import abc
from pathlib import Path

from ..watch import registry
from . import identity, role_needs, roles


def _one_shot(channel: str) -> str:
    return "--codex-thread" if channel.startswith("codex:") else "--once"


def _line(need: role_needs.Need, channel: str) -> str:
    return f"- {need.reason}: `{need.command} {_one_shot(channel)}`"


def missing(
    conn: sqlite3.Connection,
    path: Path,
    channel: str,
    is_open: abc.Callable[[roles.PR], bool],
) -> list[role_needs.Need]:
    """The waiters the brief at *path* needs and *channel* isn't running."""
    try:
        lemon_id = identity.read(path.read_text())
    except (OSError, ValueError):
        return []

    if not lemon_id:
        return []

    return role_needs.missing(
        role_needs.required(conn, lemon_id, path.read_text(), is_open),
        lambda kind, target: bool(registry.mine(channel, kind, target)),
    )


def report(
    conn: sqlite3.Connection,
    path: Path,
    channel: str,
    is_open: abc.Callable[[roles.PR], bool],
) -> str:
    """What to arm, or "" when every waiter the lemon's roles imply is running."""
    needs = missing(conn, path, channel, is_open)
    if not needs:
        return ""

    return "\n".join(
        [
            "Your roles need waiters that aren't running. Start each as a background task "
            "(run_in_background for Claude) and list it under `## Waiters` in your brief:",
            *(_line(need, channel) for need in needs),
            "Then end your turn.",
        ]
    )
