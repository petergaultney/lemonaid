"""Claude Code session watcher backend.

Provides Claude-specific functions for the unified watcher:
- get_session_path: Find transcript files
- describe_activity: Describe what Claude is doing
- should_dismiss: Detect when to auto-dismiss notifications
"""

from pathlib import Path

from ..lemon_watchers import short_filename

# Channel prefix for Claude notifications
CHANNEL_PREFIX = "claude:"


def get_session_path(session_id: str, cwd: str) -> Path | None:
    """Find the transcript path, trying parent directories as fallback.

    Claude may store sessions under a parent directory (like git root) rather
    than the exact cwd. This handles git worktrees where sessions live under
    the main repo path.
    """
    if not cwd or not session_id:
        return None

    from . import find_project_path

    project_path = find_project_path(cwd)
    if not project_path:
        return None

    transcript_path = project_path / f"{session_id}.jsonl"
    return transcript_path if transcript_path.exists() else None


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what Claude is doing.

    Returns a short description like "Reading src/file.py" or "Running tests",
    or None if this entry doesn't have describable content.
    """
    entry_type = entry.get("type")

    if entry_type != "assistant":
        return None

    message = entry.get("message", {})
    content = message.get("content", [])

    if isinstance(content, list):
        # First look for tool use - most specific
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return _describe_tool_use(block)

        # Then check for text response
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text.strip():
                    first_line = text.strip().split("\n")[0][:60]
                    if len(first_line) < len(text.strip().split("\n")[0]):
                        first_line += "..."
                    return first_line

    return None


def should_dismiss(entry: dict) -> bool:
    """Check if a transcript entry indicates we should dismiss the notification.

    Returns True for:
    - assistant entries (Claude is working)
    - user entries with actual user messages (user provided input)
    """
    entry_type = entry.get("type")

    if entry_type == "assistant":
        return True

    if entry_type == "user":
        message = entry.get("message", {})
        content = message.get("content")
        # Real user messages have string content (not tool_result arrays)
        if isinstance(content, str):
            return True

    return False


def needs_attention(entry: dict) -> bool:
    """Check if an entry indicates the agent is waiting for user input.

    For Claude, this is handled by the notification hooks (Stop, Notification),
    so we always return False here - the watcher doesn't need to mark as unread.
    """
    return False


def _describe_tool_use(block: dict) -> str:
    """Describe a tool_use block in human-readable form."""
    tool_name = block.get("name", "unknown")
    tool_input = block.get("input", {})

    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"Reading {short_filename(path)}"

    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        return f"Editing {short_filename(path)}"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if cmd:
            short_cmd = cmd.split()[0] if cmd.split() else cmd[:40]
            return f"Running {short_cmd}"
        return "Running command"

    if tool_name in ("Grep", "Glob"):
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"Searching for {pattern[:30]}"
        return "Searching"

    if tool_name == "Task":
        desc = tool_input.get("description", "")
        if desc:
            return f"Task: {desc[:40]}"
        return "Running task"

    if tool_name == "WebFetch":
        return "Fetching web content"

    if tool_name == "WebSearch":
        query = tool_input.get("query", "")
        if query:
            return f"Searching: {query[:30]}"
        return "Web search"

    return f"Using {tool_name}"
