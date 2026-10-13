"""Optional Stop hook: a lemon may not end its turn without the waiters its roles imply.

Separate from `waiter-check`, which enforces the inbox and children waiters. Registered
only when the user adds it (`lemonaid claude hooks --role-waiters`).
"""

import json
import sys
import time

from ..brief import handoff_state, role_report
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id
from ..log import get_logger
from ..watch import pr_open
from . import waiter_check

_log = get_logger("claude.role_waiters")


def reason_to_block(data: dict) -> str:
    """The reason to block this Stop, or "" to let it through."""
    path = waiter_check.attached_brief(data)
    if path is None:
        return ""

    try:
        channel = channel_id("claude", data.get("session_id"))
    except UnidentifiedSession:
        return ""

    with db.connect() as conn:
        if handoff_state.pending_source(conn, path, channel, time.time()):
            return ""

        return role_report.report(conn, path, channel, lambda pr: pr_open.is_open(*pr))


def handle(stdin_data: str | None = None) -> None:
    try:
        data = json.loads(stdin_data if stdin_data is not None else sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    reason = reason_to_block(data)
    if not reason or data.get("stop_hook_active"):
        if reason:
            _log.warning("letting %s stop after one block: %s", data.get("session_id"), reason)
        return

    _log.info("blocked a stop for %s: %s", data.get("session_id"), reason)
    print(json.dumps({"decision": "block", "reason": reason}))
