"""Whether a lemon's conversation is still on disk for its harness to resume."""

from collections import abc

from ..claude import session_socket
from ..codex import channels, threads
from . import db


def _claude_missing(row: db.Notification) -> bool:
    session = str(row.metadata.get("session_id") or "")
    return not session or not any(session_socket.claude_dir().glob(f"projects/*/{session}.jsonl"))


def missing(rows: abc.Iterable[db.Notification]) -> set[str]:
    """The channels of *rows* whose conversation is gone, so a resume would start an empty one
    under the lemon's name. Codex answers for all the Codex rows at once."""
    rows = list(rows)
    codex = {
        row.channel: channels.thread(row.channel)
        for row in rows
        if row.channel.startswith("codex:")
    }
    gone = threads.gone(codex.values())
    return {
        *(channel for channel, thread in codex.items() if thread in gone),
        *(
            row.channel
            for row in rows
            if row.channel.startswith("claude:") and _claude_missing(row)
        ),
    }


def transcript_missing(row: db.Notification) -> bool:
    return row.channel in missing([row])
