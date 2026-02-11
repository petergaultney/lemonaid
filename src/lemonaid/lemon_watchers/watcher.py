"""Unified session watcher infrastructure.

Provides shared watcher loop logic that can be used by multiple backends
(Claude, Codex, etc.) to monitor session files for activity.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..log import get_logger

_log = get_logger("watcher")


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

    @staticmethod
    def needs_attention(entry: dict) -> bool:
        """Check if an entry indicates the agent is waiting for user input.

        Optional method - returns False by default for backends that don't need it
        (e.g., Claude/Codex where hooks fire when attention is needed).
        """
        ...


def read_jsonl_tail(path: Path, max_bytes: int = 64 * 1024) -> list[str]:
    """Read the last N bytes of a JSONL file and return lines.

    Seeks to the end minus max_bytes, skips the first partial line,
    and returns all complete lines.
    """
    try:
        file_size = path.stat().st_size
        read_size = min(file_size, max_bytes)

        with open(path, encoding="utf-8", errors="replace") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()  # Skip partial line
            content = f.read()

        return content.strip().split("\n")
    except (OSError, UnicodeDecodeError):
        return []


def parse_timestamp(ts_str: str) -> float | None:
    """Parse an ISO timestamp string to Unix timestamp."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def is_process_running_on_tty(tty: str, process_name: str = "claude") -> bool:
    """Check if a process is running on the given TTY.

    Args:
        tty: TTY path like "/dev/ttys002" or "ttys002"
        process_name: Process name to search for (default: "claude")

    Returns:
        True if the process is running on that TTY
    """
    # Normalize TTY name (remove /dev/ prefix if present)
    tty_name = tty.replace("/dev/", "")
    if not tty_name:
        return True  # Can't check, assume alive

    try:
        result = subprocess.run(
            ["ps", "-t", tty_name, "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return process_name in result.stdout
    except (subprocess.TimeoutExpired, OSError):
        return True  # On error, assume alive to avoid false archiving


def get_latest_activity(
    session_path: Path,
    describe_activity: Callable[[dict], str | None],
) -> tuple[str, str] | None:
    """Get the most recent describable activity from a session file.

    Returns (message, timestamp) tuple, or None if no activity found.
    The timestamp can be used to detect genuinely new activity.
    """
    lines = read_jsonl_tail(session_path)

    # Most recent first, limit to last 50 entries
    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            activity = describe_activity(entry)
            if activity:
                ts = entry.get("timestamp", "")
                return (activity, ts)
        except json.JSONDecodeError:
            continue

    if lines:
        _log.info("no activity found in %s (%d lines)", session_path.name, len(lines))

    return None


def has_activity_since(
    session_path: Path,
    since_time: float,
    should_dismiss: Callable[[dict], bool],
) -> dict | None:
    """Check if session has dismiss-worthy activity since given timestamp.

    Returns the triggering entry if found, None otherwise.
    """
    lines = read_jsonl_tail(session_path)

    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            ts = parse_timestamp(entry.get("timestamp", ""))
            if ts and ts > since_time and should_dismiss(entry):
                return entry
        except json.JSONDecodeError:
            continue

    return None


def check_needs_attention(
    session_path: Path,
    since_time: float,
    needs_attention: Callable[[dict], bool],
) -> dict | None:
    """Check if session has an entry indicating the agent needs user attention.

    Scans recent entries for "turn complete" signals (e.g., OpenClaw's stopReason: "stop").
    Returns the triggering entry if found, None otherwise.
    """
    lines = read_jsonl_tail(session_path)

    for line in reversed(lines[-50:]):
        try:
            entry = json.loads(line)
            ts = parse_timestamp(entry.get("timestamp", ""))
            if ts and ts > since_time and needs_attention(entry):
                return entry
        except json.JSONDecodeError:
            continue

    return None


def _check_pane_exists(tty: str, switch_source: str | None) -> bool:
    """Check if a pane still exists for the given TTY and switch source.

    Deferred import to avoid circular dependencies.
    """
    if not switch_source:
        return True  # Can't check, assume exists

    from ..handlers import check_pane_exists_by_tty

    return check_pane_exists_by_tty(tty, switch_source)


def _archive_stale_sessions(
    active: list[tuple[str, str, str, float, bool, str | None, str, str | None]],
    archive_channel: Callable[[str], None],
) -> set[str]:
    """Archive stale sessions based on TTY occupancy and pane existence.

    For each TTY:
    - If pane no longer exists: archive immediately (most reliable check)
    - If process is running: only one session can be active, archive others
    - If process is not running: archive all sessions on that TTY

    Returns set of archived channel names.
    """
    archived: set[str] = set()

    # First pass: archive any sessions whose panes no longer exist
    remaining = []
    for item in active:
        channel, _session_id, _cwd, _created_at, _is_unread, tty, _db_message, switch_source = item
        if tty and switch_source and not _check_pane_exists(tty, switch_source):
            archive_channel(channel)
            archived.add(channel)
            _log.info("archived (pane gone): %s", channel)
        else:
            remaining.append(item)

    # Second pass: group by TTY and handle duplicates/process exit
    tty_groups: dict[tuple[str, str], list[tuple[str, float]]] = {}

    for (
        channel,
        _session_id,
        _cwd,
        created_at,
        _is_unread,
        tty,
        _db_message,
        _switch_source,
    ) in remaining:
        if not tty:
            continue

        if channel.startswith("claude:"):
            process_name = "claude"
        elif channel.startswith("openclaw:"):
            process_name = "openclaw"
        else:
            process_name = "codex"
        key = (tty, process_name)

        if key not in tty_groups:
            tty_groups[key] = []
        tty_groups[key].append((channel, created_at))

    # Process each TTY group
    for (tty, process_name), sessions in tty_groups.items():
        if len(sessions) == 1:
            # Only one session - check if process is still running
            channel, _ = sessions[0]
            if not is_process_running_on_tty(tty, process_name):
                archive_channel(channel)
                archived.add(channel)
                _log.info("archived (process exited): %s", channel)
        else:
            # Multiple sessions on same TTY - keep newest, archive rest
            # Sort by created_at descending (newest first)
            sessions.sort(key=lambda x: x[1], reverse=True)
            newest_channel = sessions[0][0]

            # Check if process is running
            process_running = is_process_running_on_tty(tty, process_name)

            for channel, _ in sessions[1:]:  # Skip newest
                archive_channel(channel)
                archived.add(channel)
                _log.info("archived (newer session on %s): %s", tty, channel)

            # If process isn't running, also archive the newest
            if not process_running:
                archive_channel(newest_channel)
                archived.add(newest_channel)
                _log.info("archived (process exited): %s", newest_channel)

    return archived


def unified_watch_loop(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool, str | None, str, str | None]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    archive_channel: Callable[[str], None] | None = None,
    mark_unread: Callable[[str], int] | None = None,
    poll_interval: float = 0.5,
) -> None:
    """Main watch loop - polls all active sessions across all backends.

    Args:
        backends: List of watcher backends (claude, codex, etc.)
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread, tty, db_message, switch_source)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        archive_channel: Optional callback to archive a channel when session exits
        mark_unread: Optional callback to mark a channel as needing attention (for backends like OpenClaw)
        poll_interval: How often to poll (seconds)
    """
    # Build prefix -> backend mapping
    backend_map = {b.CHANNEL_PREFIX: b for b in backends}
    _log.info("watcher started with backends: %s", list(backend_map.keys()))

    # Track last observed transcript timestamp per channel (as unix float)
    # Used to detect genuinely new activity vs polling same state
    last_observed_ts: dict[str, float] = {}
    # Track last "needs attention" timestamp per channel to avoid re-marking
    last_attention_ts: dict[str, float] = {}
    # Cache session paths
    session_cache: dict[str, Path] = {}

    while True:
        try:
            active = get_active()

            # Archive stale sessions: group by TTY and keep only the newest per TTY
            if archive_channel:
                archived_channels = _archive_stale_sessions(active, archive_channel)
                # Remove archived channels from active list
                active = [s for s in active if s[0] not in archived_channels]
                # Clean up caches for archived channels
                for channel in archived_channels:
                    last_observed_ts.pop(channel, None)
                    # Find and remove from session_cache
                    to_remove = [k for k in session_cache if k.startswith(f"{channel}:")]
                    for k in to_remove:
                        session_cache.pop(k, None)

            for (
                channel,
                session_id,
                cwd,
                created_at,
                is_unread,
                _tty,
                _db_message,
                _switch_source,
            ) in active:
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
                if is_unread:
                    dismiss_entry = has_activity_since(
                        session_path, created_at, backend.should_dismiss
                    )
                    if dismiss_entry:
                        entry_type = dismiss_entry.get("type", "?")
                        entry_ts = dismiss_entry.get("timestamp", "")[:19]
                        mark_read(channel)
                        _log.info(
                            "marked read: %s (trigger: %s at %s)", channel, entry_type, entry_ts
                        )

                # For read notifications, check if agent now needs attention
                # (only for backends that implement needs_attention, like OpenClaw)
                if not is_unread and mark_unread:
                    needs_attention_fn = getattr(backend, "needs_attention", None)
                    if needs_attention_fn:
                        # Use the last attention timestamp we processed, or created_at
                        since_ts = last_attention_ts.get(channel, created_at)
                        attention_entry = check_needs_attention(
                            session_path, since_ts, needs_attention_fn
                        )
                        if attention_entry:
                            entry_ts_str = attention_entry.get("timestamp", "")
                            entry_ts = parse_timestamp(entry_ts_str)
                            if entry_ts:
                                last_attention_ts[channel] = entry_ts
                            mark_unread(channel)
                            _log.info(
                                "marked unread: %s (agent waiting at %s)",
                                channel,
                                entry_ts_str[:19],
                            )

                # Update message from transcript only if there's genuinely new activity.
                # We cache the timestamp of the last entry to detect new vs same state.
                # If timestamp unchanged, we don't write - this preserves whatever is
                # in the DB (e.g., a late "Permission needed" from notify handler).
                # When Claude makes progress, new entries arrive with new timestamps.
                result = get_latest_activity(session_path, backend.describe_activity)
                if result:
                    message, entry_ts_str = result
                    entry_ts = parse_timestamp(entry_ts_str)
                    if entry_ts and entry_ts != last_observed_ts.get(channel):
                        update_message(channel, message)
                        last_observed_ts[channel] = entry_ts
                        _log.info("updated %s: %s", channel, message)

        except Exception as e:
            _log.error("error: %s", e, exc_info=True)

        time.sleep(poll_interval)


_watcher_thread: threading.Thread | None = None


def start_unified_watcher(
    backends: list[WatcherBackend],
    get_active: Callable[[], list[tuple[str, str, str, float, bool, str | None, str, str | None]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    archive_channel: Callable[[str], None] | None = None,
    mark_unread: Callable[[str], int] | None = None,
) -> None:
    """Start the unified session watcher daemon thread.

    Args:
        backends: List of watcher backends to monitor
        get_active: Callback returning list of (channel, session_id, cwd, created_at, is_unread, tty, db_message, switch_source)
        mark_read: Callback to mark a channel as read
        update_message: Callback to update message for a channel
        archive_channel: Optional callback to archive a channel when session exits
        mark_unread: Optional callback to mark a channel as needing attention
    """
    global _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return  # Already running

    _watcher_thread = threading.Thread(
        target=unified_watch_loop,
        args=(backends, get_active, mark_read, update_message, archive_channel, mark_unread),
        daemon=True,
    )
    _watcher_thread.start()
