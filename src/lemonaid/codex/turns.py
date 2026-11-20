"""A Codex lemon's turns and what it is doing, recorded from Codex's hooks.

UserPromptSubmit starts a turn, PreToolUse says what it is doing, and the notify hook's
turn-complete or the Interrupt hook ends it. Codex runs these hooks concurrently, so each
carries its turn's ID: a late report of an ended turn doesn't reopen it, and a late
interrupt doesn't end the turn after it. Why they run async rather than in order:
docs/decisions/codex-turn-hooks-run-async.md. PostModelRequest gives the context used.
Every hook also names the model.
"""

import json
import re
import time
import typing as ty

from ..inbox import db
from ..log import get_logger
from . import channels, queued

_log = get_logger("codex.turns")

_PATCHED = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.MULTILINE)
_LONGEST = 120


def _command(tool_input: ty.Any) -> str:
    command = tool_input.get("command") if isinstance(tool_input, dict) else tool_input
    if isinstance(command, list):
        return command[-1] if len(command) >= 3 else " ".join(map(str, command))
    return command if isinstance(command, str) else ""


def describe(tool_name: str, tool_input: ty.Any) -> str:
    """What a lemon is doing, from the tool it is about to use."""
    if tool_name == "Bash":
        command = _command(tool_input).strip()
        if not command:
            return "Running command"
        return (
            f"Running: {command[: _LONGEST - 3]}..."
            if len(command) > _LONGEST
            else f"Running: {command}"
        )

    if tool_name == "apply_patch":
        files = _PATCHED.findall(_command(tool_input) or json.dumps(tool_input))
        return f"Editing {', '.join(files[:3])}" if files else "Editing files"

    if tool_name.startswith("mcp__"):
        return f"Using {tool_name.rsplit('__', 1)[-1]}"

    return f"Using {tool_name}" if tool_name else "Working..."


def _channel(conn, data: dict) -> str:
    thread = data.get("session_id")
    if not isinstance(thread, str) or not thread:
        return ""

    channel = channels.channel(thread)
    return channel if db.get_by_channel(conn, channel, unread_only=False) else ""


def record(data: dict) -> None:
    """Record the turn state one of Codex's hooks reports, for the lemon that has a row."""
    event = data.get("hook_event_name")
    turn = data.get("turn_id") if isinstance(data.get("turn_id"), str) else ""
    now = time.time()
    with db.connect() as conn:
        if not (channel := _channel(conn, data)):
            return

        if isinstance(model := data.get("model"), str) and model:
            db.record_model(conn, channel, "openai", model)
        if event == "UserPromptSubmit":  # its user is back, so the row has been seen
            if db.start_turn(conn, channel, turn, now, seen=True):
                db.update_message(conn, channel, "Working...")
        elif event == "PreToolUse":
            if db.start_turn(conn, channel, turn, now):
                db.update_message(
                    conn,
                    channel,
                    describe(str(data.get("tool_name") or ""), data.get("tool_input")),
                )
        elif event == "Interrupt":
            db.record_turn_end(conn, channel, turn, now, interrupted=True)
        elif event == "PostModelRequest" and isinstance(usage := data.get("token_usage"), dict):
            # Every input token is in the context; Codex reports no window size.
            db.record_context(conn, channel, int(usage.get("input_tokens") or 0), 0)
    _log.info("recorded %s: channel=%s", event, channel)


def superseded(row: db.Notification | None, turn: str) -> bool:
    """Whether a turn later than *turn* has started or ended, so a report that *turn*
    ended is stale."""
    if row is None or not turn:
        return False

    return turn < max(str(row.metadata.get(key) or "") for key in ("turn_id", "turn_ended_id"))


def last_end(row: db.Notification) -> queued.TurnEnd | None:
    """How the lemon's last turn ended; None while one runs or none has ended."""
    at = row.metadata.get("turn_ended_at")
    if row.turn_at is not None or not isinstance(at, int | float):
        return None

    return queued.TurnEnd(float(at), bool(row.metadata.get("turn_interrupted")))
