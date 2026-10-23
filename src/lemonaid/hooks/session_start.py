"""SessionStart guidance for the one watcher attached lemons arm each turn."""

import json
import sys
import time
from pathlib import Path

from .. import brief
from ..brief import handoff_clear
from ..inbox import db
from ..inbox.channel import channel_id
from ..lemon_watchers import get_tty
from ..log import get_logger
from ..watch import codex_scout, own_edits, push_scout
from . import session_gate, stop_check

_log = get_logger("hooks.session_start")

# `lemonaid claude session-start` registers the new session's row; Claude runs it beside this hook.
_ROW_WAIT_SECONDS = 3


def _carry_across_clear(session_id: str) -> str:
    """The channel that `/clear` ended, once its brief belongs to *session_id*; else ""."""
    tty = get_tty()
    if not tty:
        return ""

    channel = channel_id("claude", session_id)
    with db.connect() as conn:
        found = handoff_clear.cleared(conn, channel, tty, time.time())
        if found is None:
            return ""

        source, path = found
        deadline = time.monotonic() + _ROW_WAIT_SECONDS
        while (
            db.get_by_channel(conn, channel, unread_only=False) is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.1)
        if not handoff_clear.carry(conn, source, path, channel):
            _log.warning("kept %s on %s after /clear; %s took no brief", path, source, channel)
            return ""

    _log.info("moved %s from %s to %s after /clear", path, source, channel)
    return source


def _pushed(path: Path, session_id: str) -> bool:
    try:
        lemon_id = brief.identity.read(path.read_text())
    except (OSError, ValueError):
        return False

    # The session normally lists its socket before this hook runs; allow a moment in case it lags.
    return (
        bool(lemon_id)
        and push_scout.ensure(session_id, lemon_id, grace=3, wait=2)
        and push_scout.running(lemon_id, session_id)
    )


def _not_pushing(path: Path, session_id: str, harness: str) -> str:
    try:
        lemon_id = brief.identity.read(path.read_text())
    except (OSError, ValueError):
        return ""

    notice = (
        push_scout.not_pushing(session_id, lemon_id) if harness == "claude" and lemon_id else ""
    )
    return f"{notice} " if notice else ""


def context(data: dict, harness: str) -> str:
    session = data.get("session_id")
    cleared = (
        _carry_across_clear(session)
        if harness == "claude" and session and data.get("source") == "clear"
        else ""
    )
    path = stop_check.attached_brief(data, harness)
    if session:
        session_gate.mark(own_edits.root(), f"{harness}-{session}", path)
    if path is None:
        return ""

    moved = (
        f"lemonaid moved your brief and inbox name here from {cleared}, the session before /clear. "
        if cleared
        else ""
    )
    if (harness == "claude" and _pushed(path, session or "")) or (
        harness == "codex" and session and codex_scout.ensure_for(session, path)
    ):
        return (
            moved + f"Your brief is {path}. Read it and the current state of your work first. "
            "lemonaid is watching for you: it reads your Watching section, PRs, Docs, children "
            "and inbox, and pushes every pending change into this session together. Handle "
            "each batch as it arrives. "
            "Keep document rows watched while this session exists, including when its Status is done."
        )

    return (
        moved
        + _not_pushing(path, session or "", harness)
        + f"Your brief is {path}. Read it and the current state of your work first. "
        f"Check `lemonaid watch --self --status`; if none is running, {stop_check.ARM[harness]} "
        "It reads your Watching section, PRs, Docs, children and inbox, reports every pending "
        "change together, and exits. Handle the whole batch and rearm it before ending that turn. "
        "Keep document rows watched while this session exists, including when its Status is done."
    )


def handle(harness: str) -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return

    if not isinstance(data, dict) or not (text := context(data, harness)):
        return

    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        )
    )
