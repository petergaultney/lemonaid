"""SessionStart hook: remind a lemon with an attached brief to arm the waiters it lists.

A lemon starting, resuming or coming back from compaction reads its work from the brief,
but nothing tells it that its waiters died with its last process. The reminder goes in as
`additionalContext`, which Claude Code and Codex both add to the session.
"""

import json
import sys

from ..brief import status, waiters
from ..claude import waiter_check

_ARM = {
    "claude": "Start `lemonaid inbox watch --self` and each waiter below that isn't running "
    "(check with its `--status` form) as a background Bash task (run_in_background).",
    "codex": "Start each waiter below that isn't running (check with its `--status` form) "
    "with `--codex-thread`, as an escalated `exec_command` session.",
}


def context(data: dict, harness: str) -> str:
    """The reminder for this session, or "" when it has no brief or its brief is done."""
    path = waiter_check.attached_brief(data, harness)
    if path is None:
        return ""

    text = path.read_text()
    if status.split(text).status == "done":
        return ""

    listed = waiters.commands(text)
    return "\n".join(
        [
            f"Your brief is {path}. {_ARM[harness]}",
            *(f"- `{command}`" for command in listed),
            *([] if listed else ["(Its `## Waiters` lists none.)"]),
        ]
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
