"""The brief attached to the session a hook fires for, in either harness."""

from pathlib import Path

from .. import brief
from ..codex import channels
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id, full_channel_id


def channel(harness: str, session_id: str | None) -> str:
    """Raises `UnidentifiedSession` without a session ID."""
    if harness == "codex":
        full_channel_id(harness, session_id)  # Keep rejecting unidentified hooks.
        with db.connect() as conn:
            brief.attached.claim_pending(conn)
            found = channels.for_session(conn, session_id)
            if not brief.attached.by_channel(conn, [found]).get(found):
                # Stop precedes the first turn-complete notification. An attached
                # transient row may not have acquired its root metadata yet.
                from .. import handlers

                locations = handlers.codex_tmux_locations()
                if locations and session_id in locations:
                    handlers.repair_tmux_locations(conn, {session_id: locations[session_id]})
                    found = channels.for_session(conn, session_id)
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
