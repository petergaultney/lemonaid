"""Stop hook: a Claude lemon with a brief may not end its turn without an inbox waiter.

Nothing but the lemon's own background task can wake a Claude session, so a
lemon that forgets `lemonaid inbox watch --self` never sees its messages.
"""

import json
import sys

from .. import brief
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id
from ..log import get_logger
from ..messages import store, waiter

_log = get_logger("claude.waiter_check")

_ARM = (
    "No inbox waiter is armed for {lemon}. Start `lemonaid inbox watch --self` as a "
    "background Bash task (run_in_background), list it under `## Waiters` in your brief, "
    "then end your turn."
)


def missing_waiter(data: dict, grace: float) -> str:
    """The reason to block this Stop, or "" to let it through."""
    try:
        channel = channel_id("claude", data.get("session_id"))
    except UnidentifiedSession:
        return ""

    with db.connect() as conn:
        brief.attached.claim_pending(conn)
        path = brief.attached.by_channel(conn, [channel]).get(channel)
    if path is None or not path.is_file():
        return ""

    text = path.read_text()
    if brief.status.split(text).status == "done":
        return ""

    lemon_id = brief.identity.read(text)
    if lemon_id and waiter.is_armed(store.inbox_for_id(lemon_id), grace):
        return ""

    return _ARM.format(lemon=lemon_id or path.name)


def handle(stdin_data: str | None = None, grace: float = 3.0) -> None:
    try:
        data = json.loads(stdin_data if stdin_data is not None else sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    reason = missing_waiter(data, grace)
    if not reason:
        return

    if data.get("stop_hook_active"):
        _log.warning("letting %s stop without a waiter after one block", data.get("session_id"))
        return

    _log.info("blocked a stop for %s: no inbox waiter", data.get("session_id"))
    print(json.dumps({"decision": "block", "reason": reason}))
