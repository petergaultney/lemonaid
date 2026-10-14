"""SessionStart guidance for the one watcher attached lemons arm each turn."""

import json
import sys

from ..claude import waiter_check
from ..watch import own_edits
from . import session_gate

_ARM = {
    "claude": "Start `lemonaid watch --self` as a background Bash task (run_in_background, timeout: 2147483647).",
    "codex": "Start `lemonaid watch --self --codex-thread` as an escalated exec_command session.",
}


def context(data: dict, harness: str) -> str:
    path = waiter_check.attached_brief(data, harness)
    if session := data.get("session_id"):
        session_gate.mark(own_edits.root(), f"{harness}-{session}", path)
    if path is None:
        return ""

    return (
        f"Your brief is {path}. Read it and the current state of your work first. "
        f"Check `lemonaid watch --self --status`; if none is running, {_ARM[harness]} "
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
