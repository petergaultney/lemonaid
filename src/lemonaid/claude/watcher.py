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


def should_dismiss(entry: dict) -> bool:
    """Check if a transcript entry indicates Claude is active (should dismiss).

    Returns True for:
    - assistant entries (thinking, tool_use, text) - Claude is working
    - user entries with actual user messages (not tool_result) - user sent input
    """
    entry_type = entry.get("type")

    if entry_type == "assistant":
        return True

    if entry_type == "user":
        message = entry.get("message", {})
        content = message.get("content")
        # Real user messages have string content
        if isinstance(content, str):
            return True

    return False


def check_transcript_for_activity(transcript_path: Path, since_time: float) -> bool:
    """Check if transcript has dismiss-worthy activity since given timestamp.

    Args:
        transcript_path: Path to the .jsonl transcript
        since_time: Unix timestamp - only consider entries after this

    Returns:
        True if activity detected that should dismiss notification
    """
    try:
        file_size = transcript_path.stat().st_size
        # Only read last 64KB - enough for recent entries
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
    get_unread: Callable[
        [], list[tuple[str, str, str, float]]
    ],  # -> [(channel, session_id, cwd, created_at), ...]
    dismiss: Callable[[str], int],  # channel -> count dismissed
    poll_interval: float = 0.5,
) -> None:
    """Main watch loop - runs forever, checking transcripts for unread notifications.

    Args:
        get_unread: Callback returning list of (channel, session_id, cwd, created_at) for unread notifications
        dismiss: Callback to dismiss a channel, returns count dismissed
        poll_interval: How often to poll (seconds)
    """
    log_file = Path("/tmp/lemonaid-watcher.log")

    def log(msg: str):
        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    log("watcher started")

    while True:
        try:
            unread = get_unread()

            for channel, session_id, cwd, created_at in unread:
                if not channel.startswith("claude:"):
                    continue

                transcript_path = get_transcript_path(cwd, session_id)
                if not transcript_path:
                    continue

                if check_transcript_for_activity(transcript_path, created_at):
                    count = dismiss(channel)
                    if count > 0:
                        log(f"dismissed {channel} via transcript activity")

        except Exception as e:
            log(f"error: {e}")

        time.sleep(poll_interval)


_watcher_thread: threading.Thread | None = None


def start_watcher(
    get_unread: Callable[[], list[tuple[str, str, str, float]]],
    dismiss: Callable[[str], int],
) -> None:
    """Start the transcript watcher daemon thread.

    Args:
        get_unread: Callback returning list of (channel, session_id, cwd, created_at) for unread notifications
        dismiss: Callback to dismiss a channel, returns count dismissed
    """
    global _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _watcher_thread = threading.Thread(
        target=watch_loop,
        args=(get_unread, dismiss),
        daemon=True,
    )
    _watcher_thread.start()
