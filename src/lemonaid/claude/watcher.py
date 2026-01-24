"""Transcript watcher for Claude Code sessions.

Monitors transcript files to detect when Claude becomes active (working),
which indicates the user has provided input and notifications should be dismissed.
"""

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path


def get_transcript_path(cwd: str, session_id: str) -> Path | None:
    """Construct the transcript path from cwd and session_id."""
    if not cwd or not session_id:
        return None

    from . import get_project_path

    transcript_path = get_project_path(cwd) / f"{session_id}.jsonl"
    return transcript_path if transcript_path.exists() else None


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what Claude is doing.

    Returns a short description like "Reading src/file.py" or "Running tests",
    or None if this entry doesn't have describable content.

    Only returns descriptions for assistant entries with tool_use or text content.
    Thinking-only entries return None so we keep looking for better descriptions.
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
                    # First line, truncated
                    first_line = text.strip().split("\n")[0][:60]
                    if len(first_line) < len(text.strip().split("\n")[0]):
                        first_line += "..."
                    return first_line

    # No describable content (e.g., thinking-only entry) - return None
    # so we keep looking at other entries
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


def _describe_tool_use(block: dict) -> str:
    """Describe a tool_use block in human-readable form."""
    tool_name = block.get("name", "unknown")
    tool_input = block.get("input", {})

    # Tool-specific descriptions
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"Reading {_short_path(path)}"

    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        return f"Editing {_short_path(path)}"

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # First word of command, or first 40 chars
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

    # Generic fallback
    return f"Using {tool_name}"


def _short_path(path: str) -> str:
    """Shorten a path for display."""
    if not path:
        return "file"
    # Just the filename, or last component
    from pathlib import Path

    return Path(path).name or path[-30:]


def get_latest_activity(transcript_path: Path) -> str | None:
    """Get the most recent describable activity from a transcript.

    Returns a description of the latest tool_use or text response,
    or None if no describable activity found.
    """
    try:
        file_size = transcript_path.stat().st_size
        read_size = min(file_size, 64 * 1024)

        with open(transcript_path) as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        # Most recent first
        for line in reversed(content.strip().split("\n")[-50:]):
            try:
                entry = json.loads(line)
                activity = describe_activity(entry)
                if activity:
                    return activity
            except json.JSONDecodeError:
                continue

        return None
    except OSError:
        return None


def has_activity_since(transcript_path: Path, since_time: float) -> bool:
    """Check if transcript has dismiss-worthy activity since given timestamp."""
    try:
        file_size = transcript_path.stat().st_size
        read_size = min(file_size, 64 * 1024)

        with open(transcript_path) as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        from datetime import datetime

        for line in reversed(content.strip().split("\n")[-50:]):
            try:
                entry = json.loads(line)
                ts_str = entry.get("timestamp", "")
                if ts_str:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    if ts > since_time and should_dismiss(entry):
                        return True
            except (json.JSONDecodeError, ValueError):
                continue

        return False
    except OSError:
        return False


def watch_loop(
    get_active: Callable[
        [], list[tuple[str, str, str, float, bool]]
    ],  # -> [(channel, session_id, cwd, created_at, is_unread), ...]
    mark_read: Callable[[str], int],  # channel -> count marked
    update_message: Callable[[str, str], int],  # (channel, message) -> count updated
    poll_interval: float = 0.5,
) -> None:
    """Main watch loop - polls all active sessions and updates messages.

    Args:
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        poll_interval: How often to poll (seconds)
    """
    log_file = Path("/tmp/lemonaid-watcher.log")

    def log(msg: str):
        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    log("watcher started")

    # Track last message per channel to avoid redundant updates
    last_message: dict[str, str] = {}

    while True:
        try:
            active = get_active()

            for channel, session_id, cwd, created_at, is_unread in active:
                if not channel.startswith("claude:"):
                    continue

                transcript_path = get_transcript_path(cwd, session_id)
                if not transcript_path:
                    continue

                # For unread notifications, check if we should mark as read
                if is_unread and has_activity_since(transcript_path, created_at):
                    mark_read(channel)
                    log(f"marked read: {channel}")

                # For all active notifications, update message if changed
                message = get_latest_activity(transcript_path)
                if message and message != last_message.get(channel):
                    update_message(channel, message)
                    last_message[channel] = message
                    log(f"updated {channel}: {message}")

        except Exception as e:
            log(f"error: {e}")

        time.sleep(poll_interval)


_watcher_thread: threading.Thread | None = None


def start_watcher(
    get_active: Callable[[], list[tuple[str, str, str, float, bool]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
) -> None:
    """Start the transcript watcher daemon thread.

    Args:
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
    """
    global _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _watcher_thread = threading.Thread(
        target=watch_loop,
        args=(get_active, mark_read, update_message),
        daemon=True,
    )
    _watcher_thread.start()
