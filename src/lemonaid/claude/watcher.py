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


def get_session_path(session_id: str, cwd: str, recorded: str = "") -> Path | None:
    """Find a session's transcript.

    `recorded` is the path Claude itself reported in a hook payload, and is
    authoritative when present. The cwd-derived name is a guess at a directory
    Claude chose, and it is wrong for paths whose encoding does not round-trip -
    a session whose transcript is never found gets no message updates at all,
    which reads as a session that has gone quiet.

    Falls back to a project lookup by session id, which also covers sessions
    Claude filed under a parent directory (the git-worktree case).
    """
    if not session_id:
        return None

    if recorded:
        path = Path(recorded)
        if path.exists():
            return path

    from .projects import find_project_path, find_session_project

    if cwd:
        project_path = find_project_path(cwd)
        if project_path:
            transcript_path = project_path / f"{session_id}.jsonl"
            if transcript_path.exists():
                return transcript_path

    # find_session_project answers with the session's cwd, not its transcript
    # directory - so it feeds the same derivation, just from a cwd Claude
    # confirmed rather than the one the inbox recorded.
    found = find_session_project(session_id)
    if found and found != cwd:
        project_path = find_project_path(found)
        if project_path:
            transcript_path = project_path / f"{session_id}.jsonl"
            if transcript_path.exists():
                return transcript_path

    return None


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
                    first_line = text.strip().split("\n")[0][:200]
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
            return f"Searching for {pattern[:80]}"
        return "Searching"

    if tool_name == "Task":
        desc = tool_input.get("description", "")
        if desc:
            return f"Task: {desc[:80]}"
        return "Running task"

    if tool_name == "WebFetch":
        return "Fetching web content"

    if tool_name == "WebSearch":
        query = tool_input.get("query", "")
        if query:
            return f"Searching: {query[:80]}"
        return "Web search"

    return f"Using {tool_name}"
