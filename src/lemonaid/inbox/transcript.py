"""Whether a lemon's conversation is still on disk for its harness to resume."""

from ..claude import session_socket
from ..codex import channels, utils
from . import db


def transcript_missing(row: db.Notification) -> bool:
    """Whether the conversation a resume would reopen is gone, so a resume would start an
    empty one under the lemon's name."""
    harness = row.channel.partition(":")[0]
    if harness == "claude":
        session = str(row.metadata.get("session_id") or "")
        return not session or not any(
            session_socket.claude_dir().glob(f"projects/*/{session}.jsonl")
        )

    if harness == "codex":
        return utils.find_session_path(channels.owner_id(row.channel, row.metadata, {})) is None

    return False
