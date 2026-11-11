"""Record that a Codex session was quit, from Codex's SessionEnd hook.

Codex reports `other` for every way of quitting it (Ctrl-C twice, Ctrl-D, `/quit`,
`/exit`) and reports nothing when a signal kills it or its pane closes, so any
report is a deliberate end. With the shared app-server daemon on, the session
lives in the daemon and a quit reports nothing either.
"""

import json
import sys
import time

from ..inbox import db
from ..log import get_logger
from . import channels

_log = get_logger("codex.session_end")


def handle_session_end(stdin_data: str | None = None) -> None:
    try:
        data = json.loads(sys.stdin.read() if stdin_data is None else stdin_data or "{}")
    except json.JSONDecodeError as error:
        _log.warning("dropped a session-end hook with unreadable JSON: %s", error)
        return

    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        _log.warning("dropped a session-end hook with no session id")
        return

    with db.connect() as conn:
        channel = channels.for_session(conn, session_id)
        if not db.record_exit(conn, channel, time.time(), str(data.get("reason") or ""), True):
            _log.info("session end for %s, which the inbox has no row for", channel)
