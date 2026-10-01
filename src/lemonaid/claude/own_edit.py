"""PreToolUse and PostToolUse hook on Claude's file edits: record edits to the session's watched docs.

The installed command (`install_hooks.OWN_EDIT_COMMAND`) starts this only for a session
that has run a doc waiter and a `.md` path, so other edits never start Python.
"""

import json
import pathlib
import sys

from ..watch import doc_events, own_edits


def record(data: dict, state_dir: pathlib.Path) -> None:
    session_id, tool_use_id = data.get("session_id"), data.get("tool_use_id")
    tool_input = data.get("tool_input")
    if not (session_id and tool_use_id and isinstance(tool_input, dict)):
        return

    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return

    writer, doc = own_edits.claude_writer(session_id), pathlib.Path(path)
    if not own_edits.watched(state_dir, writer, doc):
        return

    if data.get("hook_event_name") == "PreToolUse":
        own_edits.before_edit(state_dir, writer, tool_use_id, doc)
    elif data.get("hook_event_name") == "PostToolUse":
        own_edits.after_edit(state_dir, writer, tool_use_id, doc)


def handle() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    if isinstance(data, dict):
        record(data, doc_events.default_state_dir())
