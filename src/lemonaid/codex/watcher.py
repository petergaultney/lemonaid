"""Codex CLI session watcher backend.

Provides Codex-specific functions for the unified watcher:
- get_session_path: Find session files
- describe_activity: Describe what Codex is doing
- should_dismiss: Detect when to auto-dismiss notifications
"""

from __future__ import annotations

import json
from pathlib import Path

from .utils import get_sessions_root

# Channel prefix for Codex notifications
CHANNEL_PREFIX = "codex:"

def get_session_path(session_id: str, cwd: str) -> Path | None:
    """Find a Codex session file by session ID.

    Codex stores sessions in ~/.codex/sessions/ with filenames like:
    rollout-2026-01-23T23-32-37-<uuid>.jsonl

    Note: Codex may organize sessions in date-based subdirectories
    (e.g., 2026/01/24/), so we search recursively.
    """
    if not session_id:
        return None

    root = get_sessions_root()
    if not root.exists():
        return None

    # Try exact match first (recursive search)
    pattern = f"**/*{session_id}.jsonl"
    for path in root.glob(pattern):
        if path.is_file():
            return path

    # Try partial match (first 8 chars of UUID)
    if len(session_id) >= 8:
        for path in root.rglob("*.jsonl"):
            if session_id[:8] in path.name:
                return path

    return None


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what Codex is doing.

    Codex session entries have different formats:
    - local_shell_call: Shell command execution
    - message: User/assistant messages
    - response_item with function_call: Tool calls
    """
    entry_type = entry.get("type")

    # Shell commands - most common activity
    if entry_type == "local_shell_call":
        return _describe_shell_call(entry)

    # Assistant messages with text content
    if entry_type == "message":
        role = entry.get("role")
        if role != "assistant":
            return None
        content = entry.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") in ("output_text", "text"):
                        text = block.get("text", "")
                        if text.strip():
                            first_line = text.strip().split("\n")[0][:60]
                            if len(first_line) < len(text.strip().split("\n")[0]):
                                first_line += "..."
                            return first_line

    # response_item format
    if entry_type == "response_item":
        payload = entry.get("payload", {})
        payload_type = payload.get("type")

        if payload_type == "function_call":
            return _describe_function_call(payload)

        if payload_type == "web_search_call":
            action = payload.get("action", {})
            if isinstance(action, dict):
                query = action.get("query")
                if isinstance(query, str) and query:
                    return f"Searching: {query[:30]}"
            return "Web search"

        if payload_type == "message":
            role = payload.get("role")
            if role == "assistant":
                content = payload.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "output_text":
                            text = block.get("text", "")
                            if text.strip():
                                first_line = text.strip().split("\n")[0][:60]
                                if len(first_line) < len(text.strip().split("\n")[0]):
                                    first_line += "..."
                                return first_line

    return None


def should_dismiss(entry: dict) -> bool:
    """Check if a session entry indicates we should dismiss the notification."""
    entry_type = entry.get("type")

    if entry_type == "local_shell_call":
        return True

    if entry_type == "message":
        role = entry.get("role")
        if role in ("assistant", "user"):
            return True

    if entry_type == "response_item":
        payload = entry.get("payload", {})
        payload_type = payload.get("type")
        if payload_type in ("function_call", "web_search_call", "reasoning"):
            return True
        if payload_type == "message":
            role = payload.get("role")
            if role in ("assistant", "user"):
                return True

    return False


def _describe_shell_call(entry: dict) -> str:
    """Describe a local_shell_call entry."""
    action = entry.get("action", {})
    command = action.get("command", [])

    # command is typically ["bash", "-lc", "actual command"]
    if isinstance(command, list) and len(command) >= 3:
        actual_cmd = command[-1]
    elif isinstance(command, list) and command:
        actual_cmd = " ".join(command)
    elif isinstance(command, str):
        actual_cmd = command
    else:
        return "Running command"

    return _describe_command(actual_cmd)


def _describe_command(cmd: str) -> str:
    """Describe a shell command - just show the command, truncated."""
    if not cmd:
        return "Running command"

    cmd = cmd.strip()
    if len(cmd) > 50:
        return f"Running: {cmd[:47]}..."
    return f"Running: {cmd}"


def _describe_function_call(payload: dict) -> str:
    """Describe a function_call payload."""
    name = payload.get("name", "unknown")
    args_raw = payload.get("arguments", "")
    args: dict | None = None
    if isinstance(args_raw, str) and args_raw:
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args = None

    if name == "shell_command":
        cmd = ""
        if isinstance(args, dict):
            cmd = args.get("command", "") or ""
        if cmd:
            return _describe_command(cmd)
        return "Running command"

    if name == "read_mcp_resource":
        uri = ""
        if isinstance(args, dict):
            uri = args.get("uri", "") or ""
        if uri:
            return f"Reading {uri[:30]}"
        return "Reading resource"

    return f"Using {name}"
