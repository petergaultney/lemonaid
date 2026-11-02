"""Live reads for the inspector: lemons and PR snapshots, and the fact records a checker
gets. The inspector sends lemons messages but never reads their inboxes.

Each check is a cheap local read, or the PR snapshot the scout host already keeps; the
inspector never reads GitHub itself. What a
check can't see is recorded as `unknown` or `unavailable`, never guessed, so the checker
neither grants a wait nor accuses anyone on it.
"""

import datetime
import os
import sqlite3
from pathlib import Path

from ... import brief
from ...config import load_config
from ...lemon_facts import facts
from ...lemon_watchers import owners
from ...lineage import links
from ...log import get_logger
from ...messages import recipient
from ...watch import pr_activity, pr_poller, registry
from ..checker import checker_input

_log = get_logger("tasks.live")

Fact = dict[str, str]


def state_dir() -> Path:
    return Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()


def stamp(at: float) -> str:
    return checker_input.rfc3339(datetime.datetime.fromtimestamp(at, datetime.UTC))


def fact(
    kind: str, key: str, field: str, value: str, now: float, availability: str = "known"
) -> Fact:
    return {
        "kind": kind,
        "key": key,
        "field": field,
        "value": value,
        "observed_at": stamp(now),
        "availability": availability,
    }


def lemons(conn: sqlite3.Connection) -> dict[str, facts.Facts]:
    """What lemonaid sees about every lemon with an attached brief, by Lemon-ID."""
    window = load_config().messages.autoresume_window
    running, waiters, commands = owners.running(), registry.by_lemon(conn), recipient.tty_commands()
    found: dict[str, facts.Facts] = {}
    for entry in brief.attached.everything(conn):
        if not entry.channel:
            continue

        try:
            lemon_id = brief.lemon.current(conn, brief.identity.from_path(entry.path))
        except (OSError, ValueError) as error:
            _log.warning("Skipping brief %s: %s", entry.path, error)
            continue

        found[lemon_id] = facts.gather(
            entry,
            lemon_id,
            links.parent_of(conn, lemon_id),
            window,
            running,
            waiters(entry.channel),
            commands,
        )
    return found


def fetch_pr(key: tuple[str, str]) -> pr_activity.Snapshot | None:
    """The scout host's current snapshot of a PR some lemon watches; None for any other.
    The inspector makes no GitHub calls of its own: a PR becomes evidence when a lemon names
    it in its brief, which its scout then watches."""
    return pr_activity.fetch(key[0], int(key[1]), (), source=pr_poller.snapshot)
