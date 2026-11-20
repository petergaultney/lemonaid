"""The brief attached to the session a hook fires for, in either harness."""

from pathlib import Path

from .. import brief
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id, full_channel_id


def channel(harness: str, session_id: str | None) -> str:
    """Raises `UnidentifiedSession` without a session ID."""
    if harness == "codex":
        found = full_channel_id(harness, session_id)  # Keep rejecting unidentified hooks.
        with db.connect() as conn:
            brief.attached.claim_pending(conn)
        return found
    return (
        channel_id("claude", session_id)
        if harness == "claude"
        else full_channel_id(harness, session_id)
    )


def attached(data: dict, harness: str = "claude") -> Path | None:
    """The brief attached to the hook's session, if its file exists."""
    try:
        found = channel(harness, data.get("session_id"))
    except UnidentifiedSession:
        return None

    with db.connect() as conn:
        brief.attached.claim_pending(conn)
        path = brief.attached.by_channel(conn, [found]).get(found)
    return path if path is not None and path.is_file() else None
