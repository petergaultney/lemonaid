"""A Codex lemon's turns and what it is doing, recorded from Codex's hooks.

UserPromptSubmit starts a turn, PreToolUse says what it is doing, and the notify hook's
turn-complete or the Interrupt hook ends it. Codex runs these hooks concurrently, so each
carries its turn's ID: a late report of an ended turn doesn't reopen it, and a late
interrupt doesn't end the turn after it. Why they run async rather than in order:
docs/decisions/codex-turn-hooks-run-async.md. PostModelRequest gives the context used; its window comes from the rollout.
Every hook also names the model.
"""

import json
import os
import re
import sqlite3
import time
import typing as ty
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from . import channels, queued, rollout_window

_log = get_logger("codex.turns")

_PATCHED = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.MULTILINE)
_LONGEST = 120
_TAIL_BYTES = 256 * 1024  # a turn's end is the last thing Codex writes for it
_STALE_SECONDS = 30.0  # a turn ended in an error is over within seconds


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
            # Every input token is in the context; the hook reports no window size, so the
            # rollout, which does, is read until one is recorded.
            row = db.get_by_channel(conn, channel, unread_only=False)
            known = row is not None and row.metadata.get("context_window")
            rollout = (row.metadata.get("session_path") if row else "") or data.get(
                "transcript_path"
            )
            window = 0 if known or not isinstance(rollout, str) else rollout_window.read(rollout)
            db.record_context(conn, channel, int(usage.get("input_tokens") or 0), window)
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


class _Ended(ty.NamedTuple):
    turn: str
    at: float
    error: str  # why it failed, "" for a turn that ended normally


def _last_end(path: Path) -> _Ended | None:
    """The newest turn the Codex transcript at *path* records as complete, unless a later
    one has started since; None when its tail shows neither."""
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, stream.seek(0, os.SEEK_END) - _TAIL_BYTES))
            tail = stream.read().decode("utf-8", errors="replace").splitlines()
    except OSError as error:
        _log.warning("cannot read Codex transcript %s: %s", path, error)
        return None

    started, ended = "", None
    for line in tail:
        if '"task_' not in line:
            continue

        try:
            payload = json.loads(line).get("payload") or {}
        except json.JSONDecodeError:
            _log.debug("skipped a partial line in %s", path)  # the tail's first line is cut
            continue

        turn = payload.get("turn_id")
        if not isinstance(turn, str):
            continue

        if payload.get("type") == "task_started":
            started = max(started, turn)
        elif payload.get("type") == "task_complete" and (ended is None or turn >= ended.turn):
            at = payload.get("completed_at")
            failed = payload.get("error")
            ended = _Ended(
                turn,
                float(at) if isinstance(at, int | float) else time.time(),
                str(failed.get("message") or "") if isinstance(failed, dict) else str(failed or ""),
            )
    return None if ended is None or started > ended.turn else ended


def _settle(conn: sqlite3.Connection, row: db.Notification) -> None:
    """Close *row*'s turn when Codex's transcript records that turn complete.

    Codex sends its turn-complete notification only for a turn that ends with a message from
    the model. A turn that ends in an error, such as a response OpenAI refused to show, ends
    no other way: its transcript still records `task_complete`, which is read here.
    """
    path = str(row.metadata.get("session_path") or "")
    if row.turn_at is None or not row.channel.startswith("codex:") or not path:
        return

    ended = _last_end(Path(path))
    if ended is None or ended.turn < str(row.metadata.get("turn_id") or ""):
        return

    db.record_turn_end(conn, row.channel, ended.turn, ended.at, interrupted=False)
    if ended.error:
        db.update_message(conn, row.channel, f"Turn failed: {ended.error[:_LONGEST]}")
    _log.info("closed a turn its transcript ended: channel=%s turn=%s", row.channel, ended.turn)


def settle_stale(conn: sqlite3.Connection, now: float) -> None:
    """Settle every Codex lemon whose turn has run for longer than a failed one takes."""
    for row in db.get_active(conn, switch_source=None):
        if row.turn_at is not None and now - row.turn_at > _STALE_SECONDS:
            _settle(conn, row)
