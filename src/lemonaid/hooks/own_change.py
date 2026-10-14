"""PreToolUse and PostToolUse hook: record what a lemon's own tool calls changed.

Before and after every tool call whose input names a doc the session's waiters watch (by
its file name: an Edit's path, a patch, a shell command), that doc is hashed; one that
changed in between is recorded as the lemon's own edit (own_edits). A change during any
other call, such as a long test run, is someone else's and still wakes the waiter.
After a shell call that ran `git push`, each head the push printed is recorded as the
lemon's own push (own_pushes). The installed command (install.own_change_command) starts
this only for a session that has run a doc or PR waiter.
"""

import json
import pathlib
import sys
import typing as ty
from collections import abc

from ..watch import own_edits, own_pushes


def _strings(value: ty.Any) -> abc.Iterator[str]:
    """Every string anywhere in a tool's input or response, whose shape varies by tool and harness."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def record(data: dict, harness: str, own_root: pathlib.Path) -> None:
    session_id, event = data.get("session_id"), data.get("hook_event_name")
    if not (isinstance(session_id, str) and session_id):
        return

    writer = f"{harness}-{session_id}"
    call = str(data.get("tool_use_id") or "tool")  # without an ID, calls are assumed sequential
    named = "\n".join(_strings(data.get("tool_input")))
    for doc in own_edits.watched(own_root, writer):
        if doc.name not in named:
            continue

        key = own_edits.tool_key(call, doc)
        if event == "PreToolUse":
            own_edits.before_edit(own_root, writer, key, doc)
        elif event == "PostToolUse":
            own_edits.after_edit(own_root, writer, key, doc)
    if event == "PostToolUse" and any(
        own_pushes.is_push(s) for s in _strings(data.get("tool_input"))
    ):
        own_pushes.record(
            own_root, writer, own_pushes.heads_in("\n".join(_strings(data.get("tool_response"))))
        )


def handle(harness: str) -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    if isinstance(data, dict):
        record(data, harness, own_edits.root())
