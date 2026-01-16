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


def get_tty() -> str | None:
    """Get the TTY name for this process."""
    try:
        return os.ttyname(sys.stdin.fileno())
    except OSError:
        # stdin might not be a TTY in hook context, try stdout
        try:
            return os.ttyname(sys.stdout.fileno())
        except OSError:
            return None


def shorten_path(path: str) -> str:
    """Shorten a path for display, using last 2 components."""
    cwd_path = Path(path)
    home = Path.home()

    if cwd_path.is_relative_to(home):
        display_path = "~/" + str(cwd_path.relative_to(home))
    else:
        display_path = str(cwd_path)

    parts = display_path.split("/")
    if len(parts) > 2:
        return "/".join(parts[-2:])
    return display_path


def handle_notification(stdin_data: str | None = None) -> None:
    """
    Handle a Claude Code notification from stdin.

    Reads JSON from stdin (as provided by Claude Code hooks) and adds
    a notification to the lemonaid inbox.
    """
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "unknown")
    session_id = data.get("session_id", "")
    notification_type = data.get("notification_type", "idle_prompt")

    # Build title based on notification type
    short_path = shorten_path(cwd)
    if notification_type == "idle_prompt":
        title = f"Waiting in {short_path}"
    elif notification_type == "permission_prompt":
        title = f"Permission needed in {short_path}"
    else:
        title = f"{notification_type} in {short_path}"

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

    # Add to inbox
    db.add_notification(
        channel=channel,
        title=title,
        metadata=metadata,
    )
