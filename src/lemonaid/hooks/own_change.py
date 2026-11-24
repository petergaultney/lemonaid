"""PreToolUse and PostToolUse hook: record what a lemon's own tool calls changed.

Before and after every tool call whose input names a doc the session's waiters watch (by
its file name: an Edit's path, a patch, a shell command), that doc is hashed; one that
changed in between is recorded as the lemon's own edit (own_edits). A change during any
other call, such as a long test run, is someone else's and still wakes the waiter.
After a shell call that ran `git push`, each head the push printed is recorded as the
lemon's own push (own_pushes). A push that would print no heads would wake the lemon's
own waiter, so before it runs, Claude Code's is rewritten without `-q`/`--quiet` and the
lemon told not to push quietly; one that sends stderr to /dev/null, or Codex's, is refused.
Attached briefs supply document subscriptions even between one-shot waits.
"""

import json
import pathlib
import sys

from ..config import load_config
from ..watch import own_edits, own_pushes, subscriptions
from . import session_brief, session_gate, tool_calls


def record(data: dict, harness: str, own_root: pathlib.Path) -> None:
    session_id, event = data.get("session_id"), data.get("hook_event_name")
    if not (isinstance(session_id, str) and session_id):
        return

    writer = f"{harness}-{session_id}"
    call = str(data.get("tool_use_id") or "tool")  # without an ID, calls are assumed sequential
    named = "\n".join(tool_calls.strings(data.get("tool_input")))
    docs = set(own_edits.watched(own_root, writer))
    path = session_brief.attached(data, harness)
    session_gate.mark(own_root, writer, path)
    if path:
        for spec in subscriptions.read(
            path.read_text(), pathlib.Path.cwd(), vaults=tuple(load_config().brief.vaults)
        ):
            if spec.kind == "doc":
                docs.add(pathlib.Path(spec.target[0]))
    for doc in docs:
        if doc.name not in named:
            continue

        key = own_edits.tool_key(call, doc)
        if event == "PreToolUse":
            own_edits.before_edit(own_root, writer, key, doc)
        elif event == "PostToolUse":
            own_edits.after_edit(own_root, writer, key, doc)
    if event == "PostToolUse" and any(
        own_pushes.is_push(s) for s in tool_calls.strings(data.get("tool_input"))
    ):
        own_pushes.record(
            own_root,
            writer,
            own_pushes.heads_in("\n".join(tool_calls.strings(data.get("tool_response")))),
        )


def refusal(data: dict) -> str:
    """Why this tool call must not run, or "". Only commands are read, so an edit whose text
    mentions a quiet push is not refused."""
    if data.get("hook_event_name") != "PreToolUse" or not any(
        own_pushes.hides_heads(c) for c in tool_calls.commands(data.get("tool_input"))
    ):
        return ""

    return (
        "lemonaid: run this git push without -q/--quiet and without sending stderr to "
        "/dev/null. lemonaid recognizes your own push by the refs git prints; a push that "
        "prints none wakes your own PR watch."
    )


_REWRITTEN = (
    "lemonaid removed -q/--quiet from your git push so it prints the refs it updates, which "
    "is how lemonaid tells your own push from someone else's. Don't push quietly again."
)


def rewrite(data: dict, harness: str) -> dict | None:
    """Claude Code hook output that runs a quiet push with its quiet flags removed, or None.

    No permission decision is returned, so the rewritten command goes through the session's
    normal permission check. Codex keeps the refusal for now.
    """
    tool_input = data.get("tool_input")
    if harness != "claude" or not refusal(data) or not isinstance(tool_input, dict):
        return None

    command = tool_input.get("command")
    if not isinstance(command, str) or (loud := own_pushes.loud(command)) is None:
        return None

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "command": loud},
            "additionalContext": _REWRITTEN,
        }
    }


def handle(harness: str) -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    if not isinstance(data, dict):
        return

    if output := rewrite(data, harness):
        record(data, harness, own_edits.root())
        print(json.dumps(output))
        return

    if reason := refusal(data):
        print(reason, file=sys.stderr)
        sys.exit(2)

    record(data, harness, own_edits.root())
