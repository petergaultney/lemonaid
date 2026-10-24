"""Which terminals each lemon's own process runs on.

A row records a tty, and ttys are reused, so a harness on that tty may be some
other lemon. The process says whose it is: a Claude process lists its session
in `~/.claude/sessions/<pid>.json`, and a Codex process holds its thread's
rollout open.
"""

from collections import abc

from ..claude import live_sessions
from ..codex import channels as codex_channels
from ..codex import processes
from ..inbox import db

Owners = abc.Mapping[str, set[str]]  # a session or thread id, and the ttys running it


def running() -> dict[str, set[str]] | None:
    """The ttys each running lemon is on, or None if `ps` or `lsof` couldn't say."""
    claude = live_sessions.by_tty()
    codex = processes.thread_ttys()
    if claude is None or codex is None:
        return None

    found = {thread: set(ttys) for thread, ttys in codex.items()}
    for tty, sessions in claude.items():
        for session in sessions:
            found.setdefault(session, set()).add(tty)
    return found


def owner(row: db.Notification, owners: Owners) -> str:
    """The id *owners* would know *row*'s lemon by."""
    if row.channel.startswith("codex:"):
        return codex_channels.owner_id(row.channel, row.metadata, {k: [] for k in owners})

    if session_id := row.metadata.get("session_id"):
        return session_id

    prefix = row.channel.partition(":")[2]
    matches = [o for o in owners if o.startswith(prefix)] if prefix else []
    return matches[0] if len(matches) == 1 else row.channel


def ttys(row: db.Notification, owners: Owners) -> set[str]:
    """The ttys *row*'s lemon runs on, from *owners*."""
    return set(owners.get(owner(row, owners), set()))


def on_recorded_tty(row: db.Notification, owners: Owners | None) -> bool | None:
    """Whether *row*'s own lemon runs on the tty the row records, from *owners* (as `running`
    returns them); None when *owners* is None, the row records no tty, or another lemon
    shares it (one suspended with ^Z behind the other), since then input could reach either."""
    tty = row.metadata.get("tty")
    if owners is None or not tty:
        return None

    mine = owner(row, owners)
    holders = {o for o, held in owners.items() if tty in held}
    if mine in holders:
        return True if holders == {mine} else None

    return False
