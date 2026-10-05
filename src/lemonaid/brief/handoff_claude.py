"""Read a handoff marker from the outgoing Claude session's final reply."""

from .. import auto_read
from ..claude import watcher
from ..inbox import db
from ..lemon_watchers import read_jsonl_tail


def has_ready_marker(conn, row) -> bool:
    channel = row["source"]
    if not channel.startswith("claude:"):
        return False

    notification = db.get_by_channel(conn, channel, unread_only=False)
    if notification is None:
        return False

    metadata = notification.metadata
    transcript = watcher.get_session_path(
        channel.removeprefix("claude:"),
        str(metadata.get("cwd") or ""),
        str(metadata.get("transcript_path") or ""),
    )
    if transcript is None:
        return False

    try:
        recent = list(auto_read.newest_first(read_jsonl_tail(transcript, max_bytes=256 * 1024)))
    except OSError:
        return False

    if watcher.turn_open(recent) is not False:
        return False

    marker = f"Handoff-Ready: {row['token']}"
    return marker in watcher.final_message(recent).splitlines()
