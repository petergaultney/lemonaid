"""Read a Codex lemon's ready marker and its user's exact handoff phrases from Codex."""

from collections import abc

from ...codex import channels, threads
from ...inbox import db

_PHRASE_TURNS = 5  # how far back a typed handoff phrase is still looked for


def _thread(conn, channel: str) -> str:
    notification = db.get_by_channel(conn, channel, unread_only=False)
    return "" if notification is None else channels.thread(channel)


def has_ready_marker(conn, row) -> bool:
    """A standalone ready marker in the outgoing lemon's final reply of a completed turn."""
    channel = row["source"]
    if not channel.startswith("codex:") or not (thread := _thread(conn, channel)):
        return False

    latest = threads.latest_turns(thread, 1)
    if not latest or not latest[0].completed or not latest[0].said:
        return False

    return f"Handoff-Ready: {row['token']}" in latest[0].said[-1].splitlines()


def typed(conn, channel: str, record: abc.Callable[[str], object]) -> None:
    """Pass each message the user typed in the channel's last few turns to *record*."""
    if not (thread := _thread(conn, channel)):
        return

    for turn in reversed(threads.latest_turns(thread, _PHRASE_TURNS)):
        for message in turn.typed:
            record(message)
