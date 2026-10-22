"""Stop hook: require the unified watcher for subscribed briefs in both harnesses,
and catch broken brief edits before the turn ends.
"""

import json
import sys
import time
from pathlib import Path

from .. import brief
from ..brief import handoff_state
from ..codex import channels
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, channel_id, full_channel_id
from ..log import get_logger
from ..messages import store, waiter
from ..watch import children_waiter, codex_scout, push_scout, wait_requirements, wait_state

_log = get_logger("claude.waiter_check")

ARM = {
    "claude": "Run `lemonaid watch --self --push`, which starts lemonaid's push scout and returns; "
    "only if it prints `not started`, start `lemonaid watch --self` as a background Bash task "
    "(run_in_background, timeout: 2147483647).",
    "codex": "Run `lemonaid watch --self --push` with escalated permissions, which starts "
    "lemonaid's push scout and returns; only if it prints `not started`, start "
    "`lemonaid watch --self --codex-thread` as an escalated exec_command session and rearm it "
    "after each batch.",
}

_BROKEN = (
    "`lemonaid brief check --self` finds {brief} broken:\n{problems}\n"
    "Fix it (the `lemonaid brief bullet` and `brief pr` verbs keep the layout), then end your turn."
)


def _channel(harness: str, session_id: str | None) -> str:
    """Raises `UnidentifiedSession` without a session ID."""
    if harness == "codex":
        full_channel_id(harness, session_id)  # Keep rejecting unidentified hooks.
        with db.connect() as conn:
            brief.attached.claim_pending(conn)
            channel = channels.for_session(conn, session_id)
            if not brief.attached.by_channel(conn, [channel]).get(channel):
                # Stop precedes the first turn-complete notification. An attached
                # transient row may not have acquired its root metadata yet.
                from .. import handlers

                locations = handlers.codex_tmux_locations()
                if locations and session_id in locations:
                    handlers.repair_tmux_locations(conn, {session_id: locations[session_id]})
                    channel = channels.for_session(conn, session_id)
            return channel
    return (
        channel_id("claude", session_id)
        if harness == "claude"
        else full_channel_id(harness, session_id)
    )


def attached_brief(data: dict, harness: str = "claude") -> Path | None:
    """The brief attached to the hook's session, if its file exists."""
    try:
        channel = _channel(harness, data.get("session_id"))
    except UnidentifiedSession:
        return None

    with db.connect() as conn:
        brief.attached.claim_pending(conn)
        path = brief.attached.by_channel(conn, [channel]).get(channel)
    return path if path is not None and path.is_file() else None


def _missing_waiter(path: Path, text: str, grace: float, harness: str, session_id: str) -> str:
    try:
        lemon_id = brief.identity.read(text)
    except ValueError:
        lemon_id = ""
    with db.connect() as conn:
        children = bool(children_waiter.with_briefs(conn, lemon_id)) if lemon_id else False
    required = wait_requirements.needs_unified(text, children)
    if brief.status.split(text).status == "done" and not required:
        return ""
    if lemon_id and wait_state.is_armed(lemon_id, grace):
        return ""
    if lemon_id and harness == "claude" and push_scout.ensure(session_id, lemon_id, max(grace, 3)):
        return ""
    if harness == "codex" and session_id and codex_scout.ensure_for(session_id, path):
        return ""
    if not required and harness == "codex":
        return ""
    if not required and lemon_id and waiter.is_armed(store.inbox_for_id(lemon_id), grace):
        return ""

    why = (
        f"{push_scout.not_pushing(session_id, lemon_id)} "
        if lemon_id and harness == "claude"
        else ""
    )
    return f"{why}No unified watcher is armed for {lemon_id or path.name}. Stop separate waiters with `lemonaid watch stop --self --keep-subscriptions` first. {ARM[harness]} Then end your turn."


def _broken(path: Path, text: str) -> str:
    with db.connect() as conn:
        problems = brief.check.problems(conn, path, text)
    if not problems:
        return ""

    listed = "\n".join(f"- {problem}" for problem in problems)
    return _BROKEN.format(brief=path.name, problems=listed)


def reason_to_block(data: dict, grace: float, harness: str = "claude") -> str:
    """The reason to block this Stop, or "" to let it through."""
    path = attached_brief(data, harness)
    if path is None:
        return ""

    text = path.read_text()
    try:
        channel = _channel(harness, data.get("session_id"))
    except UnidentifiedSession:
        channel = ""
    with db.connect() as conn:
        handing_off = handoff_state.pending_source(conn, path, channel, time.time())

    return "\n\n".join(
        reason
        for reason in (
            (
                ""
                if handing_off
                else _missing_waiter(path, text, grace, harness, data.get("session_id") or "")
            ),
            _broken(path, text),
        )
        if reason
    )


def handle(stdin_data: str | None = None, grace: float = 3.0, harness: str = "claude") -> None:
    try:
        data = json.loads(stdin_data if stdin_data is not None else sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    reason = reason_to_block(data, grace, harness)
    if not reason:
        return

    if data.get("stop_hook_active"):
        _log.warning("letting %s stop after one block: %s", data.get("session_id"), reason)
        return

    _log.info("blocked a stop for %s: %s", data.get("session_id"), reason)
    print(json.dumps({"decision": "block", "reason": reason}))
