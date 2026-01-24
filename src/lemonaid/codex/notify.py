"""Codex CLI notification hook handler."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ..inbox import db
from .utils import (
    extract_session_id_from_filename,
    find_latest_session_for_cwd,
    find_session_path,
    read_session_meta,
)


def get_tty() -> str | None:
    """Get the TTY name for this process or its parent."""
    # TODO: share implementation with claude.notify
    import subprocess

    # Try stdin first
    try:
        tty = os.ttyname(sys.stdin.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Try stdout
    try:
        tty = os.ttyname(sys.stdout.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Try stderr
    try:
        tty = os.ttyname(sys.stderr.fileno())
        if tty and tty != "/dev/tty":
            return tty
    except OSError:
        pass

    # Fall back to asking ps for parent's TTY (works when spawned as hook)
    try:
        result = subprocess.run(
            ["ps", "-o", "tty=", "-p", str(os.getppid())],
            capture_output=True,
            text=True,
            check=True,
        )
        tty = result.stdout.strip()
        if tty and tty != "??" and tty != "":
            return f"/dev/{tty}"
    except (subprocess.CalledProcessError, OSError):
        pass

    return None


def detect_terminal_env() -> str:
    """Detect which terminal environment we're running in."""
    if os.environ.get("TMUX"):
        return "tmux"
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    return "unknown"


def shorten_path(path: str) -> str:
    """Shorten a path for display, using last 2 components."""
    if not path:
        return "session"
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


def get_name_from_cwd(cwd: str) -> str:
    """Extract a display name from the cwd path (last component)."""
    if not cwd:
        return ""
    parts = cwd.rstrip("/").split("/")
    return parts[-1] if parts else ""


def _parse_input_messages(data: dict) -> str | None:
    messages = data.get("input-messages") or data.get("input_messages")
    if not isinstance(messages, list) or not messages:
        return None
    first = messages[0]
    if isinstance(first, dict):
        content = first.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip().split("\n")[0][:60]
    return None


def _extract_session_id(data: dict, session_path: Path | None) -> str | None:
    for key in ("session_id", "sessionId", "thread_id", "thread-id", "threadId", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    if session_path:
        session_id = extract_session_id_from_filename(session_path.name)
        if session_id:
            return session_id

        meta = read_session_meta(session_path)
        if meta and isinstance(meta.get("id"), str):
            return meta["id"]

    return None


def _resolve_session_path(
    session_id: str | None, cwd: str | None, session_path: str | None
) -> Path | None:
    if session_path:
        path = Path(session_path).expanduser()
        if path.exists():
            return path

    if session_id:
        path = find_session_path(session_id)
        if path:
            return path

    if cwd:
        return find_latest_session_for_cwd(cwd)

    return None


def _resolve_cwd(cwd: str | None, session_path: Path | None) -> str | None:
    if cwd:
        return cwd
    if session_path:
        meta = read_session_meta(session_path)
        if meta:
            return meta.get("cwd")
    return None


def handle_notification(
    stdin_data: str | None = None,
    *,
    session_id: str | None = None,
    session_path: str | None = None,
    cwd: str | None = None,
    name: str | None = None,
    message: str | None = None,
    notification_type: str | None = None,
) -> None:
    """
    Handle a Codex CLI notification from stdin or explicit args.

    Reads JSON from stdin (as provided by Codex notify) and adds
    a notification to the lemonaid inbox.
    """
    import time

    log_file = "/tmp/lemonaid-codex-notify.log"

    if stdin_data is None:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            # Codex notify passes a single JSON argument, not stdin.
            if len(sys.argv) > 1 and sys.argv[-1].lstrip().startswith("{"):
                stdin_data = sys.argv[-1]

    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] stdin: {stdin_data[:200]}\n")

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    session_path_obj = _resolve_session_path(session_id, cwd, session_path)
    session_id = session_id or _extract_session_id(data, session_path_obj)
    cwd = _resolve_cwd(cwd or data.get("cwd"), session_path_obj)
    notification_type = (
        notification_type
        or data.get("notification_type")
        or data.get("event")
        or data.get("type")
        or "agent-turn-complete"
    )

    if not message:
        short_path = shorten_path(cwd or "")
        if "approval" in notification_type or "permission" in notification_type:
            message = f"Permission needed in {short_path}"
        elif notification_type in ("agent-turn-complete", "turn-complete", "idle_prompt"):
            message = f"Waiting in {short_path}"
        else:
            message = f"{notification_type} in {short_path}"

    if not name:
        name = (
            data.get("name")
            or data.get("customTitle")
            or data.get("title")
            or _parse_input_messages(data)
            or get_name_from_cwd(cwd or "")
        )

    # Detect terminal environment
    terminal_env = detect_terminal_env()

    # Build metadata for handler
    metadata: dict[str, str] = {}
    if cwd:
        metadata["cwd"] = cwd
    if session_id:
        metadata["session_id"] = session_id
    if notification_type:
        metadata["notification_type"] = notification_type
    if session_path_obj:
        metadata["session_path"] = str(session_path_obj)
    thread_id = data.get("thread_id") or data.get("thread-id") or data.get("threadId")
    if isinstance(thread_id, str) and thread_id:
        metadata["thread_id"] = thread_id

    # Try to get TTY for pane matching
    tty = get_tty()
    if tty:
        metadata["tty"] = tty

    # Channel format: codex:<session_id_prefix>
    channel = f"codex:{session_id[:8]}" if session_id else "codex:unknown"

    # Add to inbox (upsert=True by default, so repeated notifications update timestamp)
    with db.connect() as conn:
        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            terminal_env=terminal_env if terminal_env != "unknown" else None,
        )

    with open(log_file, "a") as f:
        f.write(
            f"[{time.strftime('%H:%M:%S')}] added: channel={channel}, type={notification_type}\n"
        )


def dismiss_session(session_id: str, debug: bool = False) -> int:
    """Dismiss (mark as read) the notification for a Codex session."""
    if not session_id:
        if debug:
            print("[dismiss] no session_id provided", file=sys.stderr)
        return 0

    channel = f"codex:{session_id[:8]}"
    with db.connect() as conn:
        count = db.mark_all_read_for_channel(conn, channel)
        if debug:
            print(f"[dismiss] marked {count} notification(s) as read for {channel}", file=sys.stderr)
        return count


def handle_dismiss(debug: bool = False) -> None:
    """Dismiss (mark as read) the notification for this Codex session."""
    import time

    debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"
    log_file = "/tmp/lemonaid-codex-dismiss.log"

    stdin_raw = sys.stdin.read() or "{}"

    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] stdin: {stdin_raw[:100]}\n")

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = _extract_session_id(data, None)
    count = dismiss_session(session_id or "", debug=debug)

    with open(log_file, "a") as f:
        f.write(
            f"[{time.strftime('%H:%M:%S')}] session_id={session_id[:8] if session_id else 'NONE'}, marked={count}\n"
        )
