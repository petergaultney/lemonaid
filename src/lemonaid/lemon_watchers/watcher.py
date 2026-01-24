"""Unified session watcher infrastructure.

Provides shared watcher loop logic that can be used by multiple backends
(Claude, Codex, etc.) to monitor session files for activity.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol


class WatcherBackend(Protocol):
    """Protocol for LLM-specific watcher backends."""

    CHANNEL_PREFIX: str

    @staticmethod
    def get_session_path(session_id: str, cwd: str) -> Path | None:
        """Get the session file path for a session."""
        ...

    @staticmethod
    def describe_activity(entry: dict) -> str | None:
        """Extract a human-readable description of activity from an entry."""
        ...

    @staticmethod
    def should_dismiss(entry: dict) -> bool:
        """Check if an entry indicates the notification should be dismissed."""
        ...


def read_jsonl_tail(path: Path, max_bytes: int = 64 * 1024) -> list[str]:
    """Read the last N bytes of a JSONL file and return lines.

    Seeks to the end minus max_bytes, skips the first partial line,
    and returns all complete lines.
    """
    try:
        file_size = path.stat().st_size
        read_size = min(file_size, max_bytes)

        with open(path) as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        return content.strip().split("\n")
    except OSError:
        return []


def parse_timestamp(ts_str: str) -> float | None:
    """Parse an ISO timestamp string to Unix timestamp."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def get_latest_activity(
    session_path: Path,
    describe_activity: Callable[[dict], str | None],
) -> str | None:
    """Get the most recent describable activity from a session file."""
    lines = read_jsonl_tail(session_path)

    # Most recent first, limit to last 50 entries
    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            activity = describe_activity(entry)
            if activity:
                return activity
        except json.JSONDecodeError:
            continue

    return None


def has_activity_since(
    session_path: Path,
    since_time: float,
    should_dismiss: Callable[[dict], bool],
) -> bool:
    """Check if session has dismiss-worthy activity since given timestamp."""
    lines = read_jsonl_tail(session_path)

    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            ts = parse_timestamp(entry.get("timestamp", ""))
            if ts and ts > since_time and should_dismiss(entry):
                return True
        except json.JSONDecodeError:
            continue

    return False


def unified_watch_loop(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    poll_interval: float = 0.5,
) -> None:
    """Main watch loop - polls all active sessions across all backends.

    Args:
        backends: List of watcher backends (claude, codex, etc.)
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        poll_interval: How often to poll (seconds)
    """
    log_file = Path("/tmp/lemonaid-watcher.log")

    def log(msg: str):
        with open(log_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    # Build prefix -> backend mapping
    backend_map = {b.CHANNEL_PREFIX: b for b in backends}
    log(f"watcher started with backends: {list(backend_map.keys())}")

    # Track last message per channel to avoid redundant updates
    last_message: dict[str, str] = {}
    # Cache session paths
    session_cache: dict[str, Path] = {}

    while True:
        try:
            active = get_active()

            for channel, session_id, cwd, created_at, is_unread in active:
                # Find the right backend for this channel
                backend = None
                for prefix, b in backend_map.items():
                    if channel.startswith(prefix):
                        backend = b
                        break

                if not backend:
                    continue

                # Get session path (with caching)
                cache_key = f"{channel}:{session_id}"
                session_path = session_cache.get(cache_key)
                if not session_path or not session_path.exists():
                    session_path = backend.get_session_path(session_id, cwd)
                    if not session_path:
                        continue
                    session_cache[cache_key] = session_path

                # For unread notifications, check if we should mark as read
                if is_unread and has_activity_since(
                    session_path, created_at, backend.should_dismiss
                ):
                    mark_read(channel)
                    log(f"marked read: {channel}")

                # For all active notifications, update message if changed
                message = get_latest_activity(session_path, backend.describe_activity)
                if message and message != last_message.get(channel):
                    update_message(channel, message)
                    last_message[channel] = message
                    log(f"updated {channel}: {message}")

        except Exception as e:
            log(f"error: {e}")

        time.sleep(poll_interval)


_watcher_thread: threading.Thread | None = None


def start_unified_watcher(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
) -> None:
    """Start the unified session watcher daemon thread.

    Args:
        backends: List of watcher backends to monitor
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
    """
    global _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _watcher_thread = threading.Thread(
        target=unified_watch_loop,
        args=(backends, get_active, mark_read, update_message),
        daemon=True,
    )
    _watcher_thread.start()
