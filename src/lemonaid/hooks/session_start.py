"""SessionStart guidance for the one watcher attached lemons arm each turn."""

import json
import sys
from pathlib import Path

from .. import brief
from ..claude import waiter_check
from ..watch import own_edits, push_scout
from . import session_gate


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
    path = waiter_check.attached_brief(data, harness)
    if session := data.get("session_id"):
        session_gate.mark(own_edits.root(), f"{harness}-{session}", path)
    if path is None:
        return ""

    if harness == "claude" and _pushed(path, session or ""):
        return (
            f"Your brief is {path}. Read it and the current state of your work first. "
            "lemonaid is watching for you: it reads your Watching section, PRs, Docs, children "
            "and inbox, and pushes every pending change into this session together. Handle "
            "each batch as it arrives. "
            "Keep document rows watched while this session exists, including when its Status is done."
        )

    return (
        _not_pushing(path, session or "", harness)
        + f"Your brief is {path}. Read it and the current state of your work first. "
        f"Check `lemonaid watch --self --status`; if none is running, {waiter_check.ARM[harness]} "
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
