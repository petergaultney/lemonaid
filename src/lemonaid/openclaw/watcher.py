"""OpenClaw session watcher backend.

Provides OpenClaw-specific functions for the unified watcher:
- get_session_path: Find session files (local or remote via DB lookup)
- read_lines: Read session lines (local or remote via SSH)
- describe_activity: Describe what OpenClaw is doing
- should_dismiss: Detect when to auto-dismiss notifications

OpenClaw session entries have these types:
- message: user/assistant messages with role and content
- custom_message: extension-injected messages that enter model context
- custom: extension state excluded from model context
- compaction: persisted summaries
- branch_summary: persisted summary when navigating trees
"""

from __future__ import annotations

import functools
import shlex
import subprocess
from pathlib import Path

from ..config import load_config
from ..inbox import db
from ..lemon_watchers.watcher import read_jsonl_tail
from ..log import get_logger
from .utils import find_session_path as _find_session_path

_log = get_logger("openclaw.watcher")

CHANNEL_PREFIX = "openclaw:"


@functools.lru_cache(maxsize=1)
def _get_remote_host() -> str | None:
    """Cache remote_host lookup to avoid reloading TOML in the polling hot path."""
    return load_config().openclaw.remote_host


def _read_jsonl_tail_ssh(host: str, path: str, max_bytes: int = 64 * 1024) -> list[str]:
    """Read the last N bytes of a remote JSONL file via SSH.

    Uses `tail -c` on the remote host. Skips the first line since it may
    be a partial line from a mid-file seek. Relies on the user's SSH config
    for ControlMaster connection reuse.
    """
    try:
        quoted_path = shlex.quote(path)
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, f"tail -c {max_bytes} -- {quoted_path}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            _log.debug("ssh tail failed for %s:%s: %s", host, path, result.stderr.strip())
            return []
        content = result.stdout.strip()
        if not content:
            return []
        lines = content.split("\n")
        # Skip first line (likely partial from mid-file read)
        return lines[1:] if len(lines) > 1 else lines
    except subprocess.TimeoutExpired:
        _log.warning("ssh tail timed out for %s:%s", host, path)
        return []
    except OSError as e:
        _log.warning("ssh tail error for %s:%s: %s", host, path, e)
        return []


def read_lines(session_path: Path) -> list[str]:
    """Read recent lines from a session file, dispatching local or SSH.

    Checks config for remote_host; if set, reads via SSH.
    Otherwise falls back to local read_jsonl_tail.
    """
    remote_host = _get_remote_host()
    if remote_host:
        return _read_jsonl_tail_ssh(remote_host, str(session_path))
    return read_jsonl_tail(session_path)


def get_session_path(session_id: str, cwd: str) -> Path | None:
    """Find an OpenClaw session file by session ID.

    For remote hosts (config.openclaw.remote_host), looks up the session path
    stored in notification metadata at registration time.
    For local hosts, searches ~/.openclaw/agents/<agentId>/sessions/.
    """
    remote_host = _get_remote_host()
    if remote_host:
        channel = f"openclaw:{session_id[:8]}"
        with db.connect() as conn:
            n = db.get_by_channel(conn, channel, unread_only=False)
            if n and n.metadata.get("session_path"):
                return Path(n.metadata["session_path"])
        return None
    return _find_session_path(session_id)


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what OpenClaw is doing.

    OpenClaw session entries have different formats:
    - message: User/assistant messages with content array
    - tool_use within content: Tool invocations
    - text within content: Plain text responses
    """
    entry_type = entry.get("type")

    if entry_type == "message":
        return _describe_message(entry)

    if entry_type == "compaction":
        return "Compacting context..."

    # custom_message - extension-injected content
    if entry_type == "custom_message":
        content = entry.get("content", [])
        return _describe_content(content)

    return None


def should_dismiss(entry: dict) -> bool:
    """Check if a session entry indicates we should dismiss the notification.

    Dismiss (mark as read) when the user provides input.
    """
    entry_type = entry.get("type")

    if entry_type == "message":
        msg = entry.get("message", {})
        role = entry.get("role") or msg.get("role")

        # User input = dismiss
        if role == "user":
            return True

    return False


def needs_attention(entry: dict) -> bool:
    """Check if a session entry indicates the agent is waiting for user input.

    OpenClaw signals turn completion with stopReason: "stop" on assistant messages.
    This means the agent has finished and is waiting for the user.
    """
    entry_type = entry.get("type")

    if entry_type == "message":
        msg = entry.get("message", {})
        role = entry.get("role") or msg.get("role")
        stop_reason = entry.get("stopReason") or msg.get("stopReason")

        # Assistant message with stopReason="stop" means turn complete
        if role == "assistant" and stop_reason == "stop":
            return True

    return False


def _describe_message(entry: dict) -> str | None:
    """Describe a message entry."""
    msg = entry.get("message", {})
    role = entry.get("role") or msg.get("role")
    content = entry.get("content") or msg.get("content", [])

    if role == "assistant":
        return _describe_content(content)

    return None


def _describe_content(content: list | str) -> str | None:
    """Describe content from a message entry."""
    if isinstance(content, str):
        if content.strip():
            first_line = content.strip().split("\n")[0][:200]
            if len(first_line) < len(content.strip().split("\n")[0]):
                first_line += "..."
            return first_line
        return None

    if not isinstance(content, list):
        return None

    # Look for tool_use or text blocks
    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type")

        if block_type in ("tool_use", "toolCall"):
            return _describe_tool_use(block)

        if block_type in ("text", "output_text"):
            text = block.get("text", "")
            if text.strip():
                first_line = text.strip().split("\n")[0][:200]
                if len(first_line) < len(text.strip().split("\n")[0]):
                    first_line += "..."
                return first_line

    return None


def _describe_tool_use(block: dict) -> str:
    """Describe a tool_use block."""
    name = block.get("name") or block.get("toolName", "unknown")
    input_data = block.get("input") or block.get("arguments", {})

    # Common tool patterns (based on Claude Code tools, which OpenClaw may use)
    if name in ("Read", "read_file"):
        path = input_data.get("file_path", input_data.get("path", ""))
        if path:
            filename = Path(path).name
            return f"Reading {filename}"
        return "Reading file"

    if name in ("Edit", "edit_file"):
        path = input_data.get("file_path", input_data.get("path", ""))
        if path:
            filename = Path(path).name
            return f"Editing {filename}"
        return "Editing file"

    if name in ("Write", "write_file"):
        path = input_data.get("file_path", input_data.get("path", ""))
        if path:
            filename = Path(path).name
            return f"Writing {filename}"
        return "Writing file"

    if name in ("Bash", "shell", "shell_command"):
        cmd = input_data.get("command", "")
        if cmd:
            if len(cmd) > 120:
                return f"Running: {cmd[:117]}..."
            return f"Running: {cmd}"
        return "Running command"

    if name in ("Grep", "search", "grep"):
        pattern = input_data.get("pattern", input_data.get("query", ""))
        if pattern:
            return f"Searching: {pattern[:80]}"
        return "Searching"

    if name in ("Glob", "find_files"):
        pattern = input_data.get("pattern", "")
        if pattern:
            return f"Finding: {pattern[:80]}"
        return "Finding files"

    if name in ("WebFetch", "web_fetch", "fetch"):
        url = input_data.get("url", "")
        if url:
            return f"Fetching: {url[:80]}"
        return "Fetching URL"

    if name in ("WebSearch", "web_search"):
        query = input_data.get("query", "")
        if query:
            return f"Searching: {query[:80]}"
        return "Web search"

    return f"Using {name}"
