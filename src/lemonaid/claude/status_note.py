"""PostToolUse hook: once per turn, remind a lemon whose brief waits on Peter what it waits on.

The reminder rides as `additionalContext` on a tool call the lemon was making
anyway, so it costs no extra turn. Claude Code gives every turn, a wake from a
background task included, its own `prompt_id`; the last one seen is kept per
session, and only the first tool call of a turn looks at the brief. The installed
command (`install_hooks.STATUS_NOTE_COMMAND`) checks that file in the shell and
starts this only for a new `prompt_id`. Each note
given is appended to `<state>/status-notes.jsonl`, which `scripts/stale-status.py`
reads to tell nudged turns from the rest.
"""

import json
import sys
import time
from pathlib import Path

from .. import brief
from ..log import get_logger
from ..tmux import navigation
from . import waiter_check

_log = get_logger("claude.status_note")


def _seen(session_id: str) -> Path:
    return navigation.get_state_path() / "status-note" / session_id


def notes_log() -> Path:
    return navigation.get_state_path() / "status-notes.jsonl"


def _record(session_id: str, prompt_id: str) -> None:
    with notes_log().open("a") as log:
        log.write(json.dumps({"session_id": session_id, "prompt_id": prompt_id, "at": time.time()}))
        log.write("\n")


def note(data: dict) -> str:
    """The reminder for this tool call, or "" when this turn already had its look."""
    session_id, prompt_id = data.get("session_id") or "", data.get("prompt_id") or ""
    if not session_id or not prompt_id or data.get("agent_id"):
        return ""  # no turn to throttle by, or a subagent's call

    seen = _seen(session_id)
    try:
        if seen.read_text() == prompt_id:
            return ""
    except FileNotFoundError:
        pass
    seen.parent.mkdir(parents=True, exist_ok=True)
    seen.write_text(prompt_id)

    path = waiter_check.attached_brief(data)
    return brief.nudge.note(path.read_text()) if path else ""


def handle(stdin_data: str | None = None) -> None:
    try:
        data = json.loads(stdin_data if stdin_data is not None else sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return

    reminder = note(data)
    if not reminder:
        return

    _log.info("status note for %s, turn %s: %s", data["session_id"], data["prompt_id"], reminder)
    _record(data["session_id"], data["prompt_id"])
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": reminder,
                }
            }
        )
    )
