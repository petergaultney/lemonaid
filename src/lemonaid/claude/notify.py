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
import typing as ty
from pathlib import Path

from ..inbox import db
from ..inbox.channel import channel_id
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_git_branch,
    get_name_from_cwd,
    get_tmux_session_name,
    get_tmux_socket,
    get_tmux_window_index,
    get_tty,
    shorten_path,
)
from ..log import get_logger

_log = get_logger("claude.notify")


_NAME_MAX_LEN = 80


def _index_entry(session_id: str, cwd: str) -> dict | None:
    """Find this session's entry in Claude's sessions-index.json.

    Tries the cwd-derived project dir first, then falls back to the parent-path
    search, which is what finds worktree sessions filed under the main repo.
    """
    from .projects import find_project_path, get_project_path

    for project_dir in (get_project_path(cwd), find_project_path(cwd)):
        if project_dir is None:
            continue

        index_path = project_dir / "sessions-index.json"
        if not index_path.exists():
            continue

        try:
            data = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        for entry in data.get("entries", []):
            if entry.get("sessionId") == session_id:
                return entry

    return None


RENAME_SOURCE = "claude_rename"  # a /rename; final, nothing supersedes it
TITLE_SOURCE = "claude_index"  # an AI-generated title; a later /rename can win


class SessionName(ty.NamedTuple):
    name: str
    source: str


def _transcript_titles(session_id: str, cwd: str) -> tuple[str | None, str | None]:
    """Read the newest (customTitle, aiTitle) out of a session's transcript.

    Current Claude versions record the AI-generated conversation name as
    `type: "ai-title"` entries (field `aiTitle`) in the JSONL transcript, and a
    `/rename` as `customTitle`. Both are appended as the session progresses, so
    the last occurrence of each wins and neither exists at first-prompt time.

    sessions-index.json is not consulted here: Claude stopped maintaining it,
    so it only covers sessions from before that change.
    """
    from .projects import find_project_path, get_project_path

    for project_dir in (get_project_path(cwd), find_project_path(cwd)):
        if project_dir is None:
            continue

        transcript = project_dir / f"{session_id}.jsonl"
        if not transcript.exists():
            continue

        ai_title = None
        custom_title = None
        try:
            with open(transcript, encoding="utf-8", errors="replace") as f:
                for line in f:
                    # Cheap reject before paying for a JSON parse; these fields
                    # appear in a small minority of a large transcript's lines.
                    if "aiTitle" not in line and "customTitle" not in line:
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if title := entry.get("aiTitle"):
                        ai_title = title
                    if title := entry.get("customTitle"):
                        custom_title = title
        except OSError:
            continue

        if custom_title or ai_title:
            return custom_title, ai_title

    return None, None


def _history_rename(session_id: str) -> str | None:
    """Find the most recent `/rename` for a session in history.jsonl."""
    history_path = Path.home() / ".claude" / "history.jsonl"
    if not history_path.exists():
        return None

    rename_name = None
    try:
        for line in history_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("sessionId") == session_id:
                display = entry.get("display", "")
                if display.startswith("/rename "):
                    rename_name = display[8:].strip()
    except OSError:
        return None

    return rename_name


def resolve_session_name(session_id: str, cwd: str) -> SessionName | None:
    """Find the name Claude holds for a session, and say where it came from.

    A `/rename` always wins over the AI-generated title, whenever it happened —
    including on a session that was already auto-titled. The source is reported
    so callers can tell a settled name from one an later rename may still
    supersede.
    """
    if not session_id or not cwd:
        return None

    custom_title, ai_title = _transcript_titles(session_id, cwd)
    if custom_title:
        return SessionName(custom_title, RENAME_SOURCE)

    if rename := _history_rename(session_id):
        return SessionName(rename, RENAME_SOURCE)

    if ai_title:
        return SessionName(ai_title, TITLE_SOURCE)

    entry = _index_entry(session_id, cwd)
    if entry:
        if title := entry.get("customTitle"):
            return SessionName(title, RENAME_SOURCE)

        if summary := entry.get("summary"):
            return SessionName(summary, TITLE_SOURCE)

        if prompt := entry.get("firstPrompt"):
            truncated = prompt[:_NAME_MAX_LEN] + ("..." if len(prompt) > _NAME_MAX_LEN else "")
            return SessionName(truncated, TITLE_SOURCE)

    return None


def get_session_name(session_id: str, cwd: str) -> str | None:
    """The name Claude holds for a session, or None if it has none yet."""
    resolved = resolve_session_name(session_id, cwd)
    return resolved.name if resolved else None


def _resolve_session(data: dict, notification_type: str) -> tuple[str, str, str, str | None, dict]:
    """Resolve the inbox fields shared by the notify and submit hooks.

    Returns (channel, session_id, name, switch_source, metadata).
    """
    cwd = data.get("cwd", "unknown")
    session_id = data.get("session_id", "")

    tmux_session = get_tmux_session_name()

    # Claude's own name for the session beats anything we can derive from the
    # environment; the tmux/cwd names are placeholders until it exists.
    resolved = resolve_session_name(session_id, cwd)
    name = resolved.name if resolved else (tmux_session or get_name_from_cwd(cwd))
    name_source = resolved.source if resolved else "environment"

    # Detect switch-source (which terminal environment this notification came from)
    switch_source = detect_terminal_switch_source()

    metadata = {
        "cwd": cwd,
        "session_id": session_id,
        "notification_type": notification_type,
        "name_source": name_source,
    }

    branch = get_git_branch(cwd)
    if branch:
        metadata["git_branch"] = branch

    tty = get_tty()  # for pane matching
    if tty:
        metadata["tty"] = tty

    # Where this session sits, so a lost tmux server can be rebuilt from the
    # inbox. Absent when the hook runs outside tmux, which is why `db.add`
    # carries a previously recorded location forward rather than dropping it.
    if tmux_session:
        metadata["tmux_session"] = tmux_session

    window = get_tmux_window_index()
    if window:
        metadata["tmux_window"] = window

    # Which tmux server, not just where in it: the watcher asking whether this
    # pane still exists may be attached to a different one, where the honest
    # answer to "is it there" is "not here, and I cannot see where it is".
    socket = get_tmux_socket()
    if socket:
        metadata["tmux_socket"] = socket

    return channel_id("claude", session_id), session_id, name, switch_source, metadata


def handle_submit(stdin_data: str | None = None) -> None:
    """Register a session as working in response to a UserPromptSubmit hook.

    Surfaces the session in the inbox the moment a prompt is submitted, as a
    read/working entry (not flagged for attention). The Stop and Notification
    hooks flip it to unread when it actually wants the user.
    """
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    _log.info("submit stdin: %s", stdin_data[:200])

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    channel, session_id, name, switch_source, metadata = _resolve_session(data, "working")
    message = f"Working in {shorten_path(data.get('cwd', 'unknown'))}"

    with db.connect() as conn:
        db.register_working(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
        )

    _log.info("working: channel=%s", channel)


def handle_session_start(stdin_data: str | None = None) -> None:
    """Record a session and where it is running, from a SessionStart hook.

    The other hooks all need a turn: a session that starts, or is resumed after
    a crash, says nothing until you talk to it, so nothing knew it existed or
    which pane it was in. This one fires on startup and on resume, which is what
    makes a restored session findable without waiting for the user.

    Registered as working rather than unread. A session that has not spoken is
    not asking for anything, and a restore that filled the inbox with every
    session it started would be its own kind of noise.
    """
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    channel, _session_id, name, switch_source, metadata = _resolve_session(data, "started")
    source = data.get("source", "startup")
    metadata["session_start_source"] = source

    with db.connect() as conn:
        db.register_working(
            conn,
            channel=channel,
            message=f"Started in {shorten_path(data.get('cwd', 'unknown'))}",
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
        )

    _log.info(
        "session start (%s): channel=%s tmux=%s:%s",
        source,
        channel,
        metadata.get("tmux_session"),
        metadata.get("tmux_window"),
    )


def handle_notification(stdin_data: str | None = None) -> None:
    """
    Handle a Claude Code notification from stdin.

    Reads JSON from stdin (as provided by Claude Code hooks) and adds
    a notification to the lemonaid inbox.
    """
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    _log.info("stdin: %s", stdin_data)

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    cwd = data.get("cwd", "unknown")
    notification_type = (
        data.get("notification_type") or data.get("hook_event_name") or "idle_prompt"
    )

    short_path = shorten_path(cwd)
    # Stop means the turn ended, which is the same state idle_prompt names: the
    # session is waiting on you. It carries no notification_type of its own, so
    # without this it falls through and reports its hook's name as the message.
    if notification_type in ("idle_prompt", "Stop"):
        message = f"Waiting in {short_path}"
    elif notification_type == "permission_prompt":
        message = f"Permission needed in {short_path}"
    elif notification_type == "PermissionRequest":
        message = f"Question in {short_path}"
    else:
        message = f"{notification_type} in {short_path}"

    channel, session_id, name, switch_source, metadata = _resolve_session(data, notification_type)

    # Check existing state before upsert for logging
    with db.connect() as conn:
        existing = db.get_by_channel(conn, channel, unread_only=False)
        existing_status = existing.status if existing else None
        existing_type = existing.metadata.get("notification_type") if existing else None

        if existing:
            prev_cwd = existing.metadata.get("cwd")
            if prev_cwd and prev_cwd != cwd:
                _log.warning(
                    "cwd changed for %s: %s -> %s",
                    channel,
                    prev_cwd,
                    cwd,
                )

        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
            # Stop knows the turn ended, not what was said in it. The watcher has
            # the assistant's actual last line, and only rewrites when the
            # transcript changes - so overwriting here loses that message until
            # the session says something new.
            keep_existing_message=notification_type == "Stop",
        )

    if existing:
        _log.info(
            "upsert: channel=%s, type=%s, was=%s/%s",
            channel,
            notification_type,
            existing_status,
            existing_type,
        )
    else:
        _log.info("new: channel=%s, type=%s", channel, notification_type)


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

    channel = channel_id("claude", session_id)
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
    debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"

    stdin_raw = sys.stdin.read() or "{}"

    _log.info("dismiss stdin: %s", stdin_raw[:100])

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = data.get("session_id", "")
    count = dismiss_session(session_id, debug=debug)

    _log.info("dismiss: session_id=%s, marked=%d", session_id[:8] if session_id else "NONE", count)
