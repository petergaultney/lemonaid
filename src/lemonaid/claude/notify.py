"""Claude Code notification hook handler.

This module handles notifications from Claude Code hooks, adding them to the
lemonaid inbox for attention tracking.

Usage in Claude Code settings.json:
    {
      "hooks": {
        "Notification": [
          {
            "matcher": "idle_prompt",
            "hooks": [
              {
                "type": "command",
                "command": "lemonaid claude notify"
              }
            ]
          }
        ]
      }
    }
"""

import json
import os
import sys
from pathlib import Path

from ..inbox import db
from ..lemon_watchers import (
    detect_terminal_env,
    get_name_from_cwd,
    get_tmux_session_name,
    get_tty,
    shorten_path,
)


def get_session_name(session_id: str, cwd: str) -> str | None:
    """Look up the session name from Claude Code's data files.

    Checks sessions-index.json first, then falls back to history.jsonl
    for sessions that haven't been indexed yet.

    Returns customTitle if set, otherwise firstPrompt, otherwise None.
    """
    if not session_id or not cwd:
        return None

    from . import get_project_path

    # Try sessions-index.json first
    sessions_index_path = get_project_path(cwd) / "sessions-index.json"
    if sessions_index_path.exists():
        try:
            data = json.loads(sessions_index_path.read_text())
            entries = data.get("entries", [])

            for entry in entries:
                if entry.get("sessionId") == session_id:
                    # Prefer customTitle, fall back to firstPrompt
                    return entry.get("customTitle") or entry.get("firstPrompt")

        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to history.jsonl for sessions not yet indexed
    # Look for most recent /rename command for this session
    history_path = Path.home() / ".claude" / "history.jsonl"
    if history_path.exists():
        try:
            rename_name = None
            for line in history_path.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("sessionId") == session_id:
                        display = entry.get("display", "")
                        if display.startswith("/rename "):
                            rename_name = display[8:].strip()  # Get name after "/rename "
                except json.JSONDecodeError:
                    continue
            if rename_name:
                return rename_name
        except OSError:
            pass

    return None


def handle_notification(stdin_data: str | None = None) -> None:
    """
    Handle a Claude Code notification from stdin.

    Reads JSON from stdin (as provided by Claude Code hooks) and adds
    a notification to the lemonaid inbox.
    """
    import time

    log_file = "/tmp/lemonaid-notify.log"

    if stdin_data is None:
        stdin_data = sys.stdin.read()

    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] stdin: {stdin_data}\n")

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "unknown")
    session_id = data.get("session_id", "")
    notification_type = data.get("notification_type", "idle_prompt")

    # Build message based on notification type
    short_path = shorten_path(cwd)
    if notification_type == "idle_prompt":
        message = f"Waiting in {short_path}"
    elif notification_type == "permission_prompt":
        message = f"Permission needed in {short_path}"
    else:
        message = f"{notification_type} in {short_path}"

    # Look up session name: Claude name > tmux session name > cwd-derived name
    name = get_session_name(session_id, cwd) or get_tmux_session_name() or get_name_from_cwd(cwd)

    # Detect terminal environment
    terminal_env = detect_terminal_env()

    # Build metadata for handler
    metadata = {
        "cwd": cwd,
        "session_id": session_id,
        "notification_type": notification_type,
    }

    # Try to get TTY for pane matching
    tty = get_tty()
    if tty:
        metadata["tty"] = tty

    # Channel format: claude:<session_id_prefix>
    channel = f"claude:{session_id[:8]}" if session_id else "claude:unknown"

    # Check existing state before upsert for logging
    with db.connect() as conn:
        existing = db.get_by_channel(conn, channel, unread_only=False)
        existing_status = existing.status if existing else None
        existing_type = existing.metadata.get("notification_type") if existing else None

        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            terminal_env=terminal_env if terminal_env != "unknown" else None,
        )

    with open(log_file, "a") as f:
        if existing:
            f.write(
                f"[{time.strftime('%H:%M:%S')}] upsert: channel={channel}, "
                f"type={notification_type}, was={existing_status}/{existing_type}\n"
            )
        else:
            f.write(
                f"[{time.strftime('%H:%M:%S')}] new: channel={channel}, type={notification_type}\n"
            )


def dismiss_session(session_id: str, debug: bool = False) -> int:
    """
    Dismiss (mark as read) the notification for a Claude session.

    Args:
        session_id: The Claude Code session ID
        debug: Enable debug output

    Returns:
        Number of notifications marked as read
    """
    if not session_id:
        if debug:
            print("[dismiss] no session_id provided", file=sys.stderr)
        return 0

    channel = f"claude:{session_id[:8]}"
    with db.connect() as conn:
        count = db.mark_all_read_for_channel(conn, channel)
        if debug:
            print(
                f"[dismiss] marked {count} notification(s) as read for {channel}", file=sys.stderr
            )
        return count


def handle_dismiss(debug: bool = False) -> None:
    """
    Dismiss (mark as read) the notification for this Claude session.

    Reads session_id from stdin and marks any unread notification
    for that channel as read.

    Set LEMONAID_DEBUG=1 environment variable to enable debug output.
    Set LEMONAID_LOG_FILE to a path to write debug logs to a file.
    """
    import time

    debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"
    log_file = "/tmp/lemonaid-dismiss.log"

    stdin_raw = sys.stdin.read() or "{}"

    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] stdin: {stdin_raw[:100]}\n")

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = data.get("session_id", "")
    count = dismiss_session(session_id, debug=debug)

    with open(log_file, "a") as f:
        f.write(
            f"[{time.strftime('%H:%M:%S')}] session_id={session_id[:8] if session_id else 'NONE'}, marked={count}\n"
        )
