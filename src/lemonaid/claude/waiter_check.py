"""Stop hook: a Claude lemon with a brief may not end its turn without an inbox waiter,
or with a brief `lemonaid brief check` finds broken.

Nothing but the lemon's own background task can wake a Claude session, so a
lemon that forgets `lemonaid inbox watch --self` never sees its messages. A
brief broken by a hand edit is caught in the turn that broke it.
"""

import json
import sys
import time
from pathlib import Path

from .. import brief
from ..brief import handoff_state
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id
from ..log import get_logger
from ..messages import store, waiter
from ..watch import children_waiter

_log = get_logger("claude.waiter_check")

_ARM = (
    "No inbox waiter is armed for {lemon}. Start `lemonaid inbox watch --self` as a "
    "background Bash task (run_in_background), list it under `## Waiters` in your brief, "
    "then end your turn."
)


_WATCH = (
    "You have children and no waiter on them. "
    + children_waiter.CLAUDE_REMINDER
    + " Then end your turn."
)

_BROKEN = (
    "`lemonaid brief check --self` finds {brief} broken:\n{problems}\n"
    "Fix it (the `lemonaid brief bullet` and `brief pr` verbs keep the layout), then end your turn."
)


def attached_brief(data: dict) -> Path | None:
    """The brief attached to the hook's session, if its file exists."""
    try:
        channel = channel_id("claude", data.get("session_id"))
    except UnidentifiedSession:
        return None

    with db.connect() as conn:
        brief.attached.claim_pending(conn)
        path = brief.attached.by_channel(conn, [channel]).get(channel)
    return path if path is not None and path.is_file() else None


def _missing_waiter(path: Path, text: str, grace: float) -> str:
    if brief.status.split(text).status == "done":
        return ""

    try:
        lemon_id = brief.identity.read(text)
    except ValueError:
        lemon_id = ""  # the check reports it
    if lemon_id and waiter.is_armed(store.inbox_for_id(lemon_id), grace):
        return ""

    return _ARM.format(lemon=lemon_id or path.name)


def _unwatched_children(text: str) -> str:
    if brief.status.split(text).status == "done":
        return ""

    try:
        lemon_id = brief.identity.read(text)
    except ValueError:
        return ""

    with db.connect() as conn:
        waiting_on = children_waiter.with_briefs(conn, lemon_id)
    if not waiting_on or children_waiter.is_armed(lemon_id):
        return ""

    return _WATCH


def _broken(path: Path, text: str) -> str:
    with db.connect() as conn:
        problems = brief.check.problems(conn, path, text)
    if not problems:
        return ""

    listed = "\n".join(f"- {problem}" for problem in problems)
    return _BROKEN.format(brief=path.name, problems=listed)


def reason_to_block(data: dict, grace: float) -> str:
    """The reason to block this Stop, or "" to let it through."""
    path = attached_brief(data)
    if path is None:
        return ""

    text = path.read_text()
    try:
        channel = channel_id("claude", data.get("session_id"))
    except UnidentifiedSession:
        channel = ""
    with db.connect() as conn:
        handing_off = handoff_state.pending_source(conn, path, channel, time.time())

    return "\n\n".join(
        reason
        for reason in (
            ("" if handing_off else _missing_waiter(path, text, grace)),
            _unwatched_children(text),
            _broken(path, text),
        )
        if reason
    )


def handle(stdin_data: str | None = None, grace: float = 3.0) -> None:
    try:
        data = json.loads(stdin_data if stdin_data is not None else sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    reason = reason_to_block(data, grace)
    if not reason:
        return

    if data.get("stop_hook_active"):
        _log.warning("letting %s stop after one block: %s", data.get("session_id"), reason)
        return

    _log.info("blocked a stop for %s: %s", data.get("session_id"), reason)
    print(json.dumps({"decision": "block", "reason": reason}))
