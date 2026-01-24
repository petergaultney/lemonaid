"""Session watcher for Codex CLI sessions.

Monitors Codex session files to detect when Codex becomes active (working),
which indicates the user has provided input and notifications should be dismissed.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .utils import find_session_path


def _parse_entry(line: str) -> dict | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _payload(entry: dict) -> dict:
    payload = entry.get("payload")
    return payload if isinstance(payload, dict) else {}


def describe_activity(entry: dict) -> str | None:
    """Extract a human-readable description of what Codex is doing."""
    if entry.get("type") != "response_item":
        return None

    payload = _payload(entry)
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
        if role != "assistant":
            return None
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

    return None


def should_dismiss(entry: dict) -> bool:
    """Check if a session entry indicates we should dismiss the notification."""
    if entry.get("type") != "response_item":
        return False

    payload = _payload(entry)
    payload_type = payload.get("type")

    if payload_type in ("function_call", "web_search_call", "reasoning"):
        return True

    if payload_type == "message":
        role = payload.get("role")
        if role in ("assistant", "user"):
            return True

    return False


def _describe_function_call(payload: dict) -> str:
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
            short_cmd = cmd.split()[0] if cmd.split() else cmd[:40]
            return f"Running {short_cmd}"
        return "Running command"

    if name == "read_mcp_resource":
        uri = ""
        if isinstance(args, dict):
            uri = args.get("uri", "") or ""
        if uri:
            return f"Reading {uri[:30]}"
        return "Reading resource"

    return f"Using {name}"


def get_latest_activity(session_path: Path) -> str | None:
    """Get the most recent describable activity from a session."""
    try:
        file_size = session_path.stat().st_size
        read_size = min(file_size, 64 * 1024)

        with session_path.open() as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()
            content = f.read()

        for line in reversed(content.strip().split("\n")[-50:]):
            entry = _parse_entry(line)
            if not entry:
                continue
            activity = describe_activity(entry)
            if activity:
                return activity

        return None
    except OSError:
        return None


def has_activity_since(session_path: Path, since_time: float) -> bool:
    """Check if session has dismiss-worthy activity since given timestamp."""
    try:
        file_size = session_path.stat().st_size
        read_size = min(file_size, 64 * 1024)

        with session_path.open() as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()
            content = f.read()

        from datetime import datetime

        for line in reversed(content.strip().split("\n")[-50:]):
            entry = _parse_entry(line)
            if not entry:
                continue
            ts_str = entry.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
                if ts > since_time and should_dismiss(entry):
                    return True

        return False
    except OSError:
        return False


def watch_loop(
    get_active: Callable[[], list[tuple[str, str, str, float, bool]]],
    mark_read: Callable[[str], int],
    update_message: Callable[[str, str], int],
    poll_interval: float = 0.5,
) -> None:
    """Main watch loop - polls all active sessions and updates messages."""
    log_file = Path("/tmp/lemonaid-codex-watcher.log")

    def log(msg: str):
        with log_file.open("a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    log("watcher started")

    last_message: dict[str, str] = {}
    session_cache: dict[str, Path] = {}

    while True:
        try:
            active = get_active()

            for channel, session_id, _cwd, created_at, is_unread in active:
                if not channel.startswith("codex:"):
                    continue

                session_path = session_cache.get(session_id)
                if not session_path or not session_path.exists():
                    session_path = find_session_path(session_id)
                    if not session_path:
                        continue
                    session_cache[session_id] = session_path

                if is_unread and has_activity_since(session_path, created_at):
                    mark_read(channel)
                    log(f"marked read: {channel}")

                message = get_latest_activity(session_path)
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
    """Start the Codex session watcher daemon thread."""
    global _watcher_thread

    if _watcher_thread is not None and _watcher_thread.is_alive():
        return

    _watcher_thread = threading.Thread(
        target=watch_loop,
        args=(get_active, mark_read, update_message),
        daemon=True,
    )
    _watcher_thread.start()
