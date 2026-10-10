"""Record that a Claude session ended, and Claude's reason, from a SessionEnd hook.

The record says Claude reported an end, not that its process stopped. Its absence
says nothing on its own: the hook may not be installed, or never got to run.
"""

import json
import sys
import time

from ..inbox import db
from ..inbox.channel import channel_id
from ..log import get_logger

_log = get_logger("claude.session_end")


def handle_session_end(stdin_data: str | None = None) -> None:
    try:
        data = json.loads(sys.stdin.read() if stdin_data is None else stdin_data or "{}")
    except json.JSONDecodeError as error:
        _log.warning("dropped a session-end hook with unreadable JSON: %s", error)
        return

    session_id = data.get("session_id", "")
    if not session_id:
        _log.warning("dropped a session-end hook with no session id")
        return

    channel = channel_id("claude", session_id)
    with db.connect() as conn:
        if not db.record_exit(conn, channel, time.time(), str(data.get("reason") or "")):
            _log.info("session end for %s, which the inbox has no row for", channel)
