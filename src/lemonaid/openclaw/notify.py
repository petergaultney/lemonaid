"""OpenClaw notification hook handler.

OpenClaw may not have explicit notification hooks like Claude Code, but
this module provides the handler infrastructure in case hooks are added
or for manual triggering.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ..inbox import db
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_git_branch,
    get_name_from_cwd,
    get_tty,
    shorten_path,
)
from ..log import get_logger
from .utils import (
    extract_session_id_from_filename,
    find_most_recent_session,
    find_session_path,
    get_last_user_message,
    get_session_key,
    get_session_name,
    read_session_header,
)

_log = get_logger("openclaw.notify")


def _extract_session_id(data: dict, session_path: Path | None) -> str | None:
    """Extract session ID from data or session path."""
    for key in ("session_id", "sessionId", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    if session_path:
        session_id = extract_session_id_from_filename(session_path.name)
        if session_id:
            return session_id

        header = read_session_header(session_path)
        if header and isinstance(header.get("id"), str):
            return header["id"]

    return None


def _resolve_session_path(
    session_id: str | None, agent_id: str | None, session_path: str | None
) -> Path | None:
    """Resolve the session file path."""
    if session_path:
        path = Path(session_path).expanduser()
        if path.exists():
            return path

    if session_id:
        return find_session_path(session_id, agent_id)

    return None


def _resolve_cwd(cwd: str | None, session_path: Path | None) -> str | None:
    """Resolve the working directory."""
    if cwd:
        return cwd

    if session_path:
        header = read_session_header(session_path)
        if header:
            return header.get("cwd")

    return None


def handle_notification(
    stdin_data: str | None = None,
    *,
    session_id: str | None = None,
    agent_id: str | None = None,
    session_path: str | None = None,
    cwd: str | None = None,
    name: str | None = None,
    message: str | None = None,
    notification_type: str | None = None,
) -> None:
    """Handle an OpenClaw notification.

    Can be triggered by a hook or manually. Reads JSON from stdin
    and adds a notification to the lemonaid inbox.
    """
    if stdin_data is None:
        stdin_data = sys.stdin.read() if not sys.stdin.isatty() else ""

    _log.info("stdin: %s", stdin_data[:200])

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    agent_id = agent_id or data.get("agent_id") or data.get("agentId")
    session_path_obj = _resolve_session_path(session_id, agent_id, session_path)
    session_id = session_id or _extract_session_id(data, session_path_obj)
    cwd = _resolve_cwd(cwd or data.get("cwd"), session_path_obj)
    notification_type = (
        notification_type
        or data.get("notification_type")
        or data.get("event")
        or data.get("type")
        or "idle"
    )

    if not message:
        short_path = shorten_path(cwd or "")
        if notification_type == "idle":
            message = f"Waiting in {short_path}"
        elif "approval" in notification_type or "permission" in notification_type:
            message = f"Permission needed in {short_path}"
        else:
            message = f"{notification_type} in {short_path}"

    if not name:
        name = data.get("name") or data.get("title") or get_name_from_cwd(cwd or "")

    switch_source = detect_terminal_switch_source()

    metadata: dict[str, str] = {}
    if cwd:
        metadata["cwd"] = cwd
    if session_id:
        metadata["session_id"] = session_id
    if agent_id:
        metadata["agent_id"] = agent_id
    if notification_type:
        metadata["notification_type"] = notification_type
    if session_path_obj:
        metadata["session_path"] = str(session_path_obj)

    branch = get_git_branch(cwd or "")
    if branch:
        metadata["git_branch"] = branch
    if agent_id and session_id:
        session_key = get_session_key(agent_id, session_id)
        if session_key:
            metadata["session_key"] = session_key
    tty = get_tty()
    if tty:
        metadata["tty"] = tty

    # Channel format: openclaw:<session_id_prefix>
    channel = f"openclaw:{session_id[:8]}" if session_id else "openclaw:unknown"

    with db.connect() as conn:
        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
        )

    _log.info("added: channel=%s, type=%s", channel, notification_type)


def dismiss_session(session_id: str, debug: bool = False) -> int:
    """Dismiss (mark as read) the notification for an OpenClaw session."""
    if not session_id:
        if debug:
            print("[dismiss] no session_id provided", file=sys.stderr)
        return 0

    channel = f"openclaw:{session_id[:8]}"
    with db.connect() as conn:
        count = db.mark_all_read_for_channel(conn, channel)
        if debug:
            print(
                f"[dismiss] marked {count} notification(s) as read for {channel}", file=sys.stderr
            )
        return count


def handle_dismiss(debug: bool = False) -> None:
    """Dismiss (mark as read) the notification for this OpenClaw session."""
    _debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"

    stdin_raw = (sys.stdin.read() if not sys.stdin.isatty() else "{}") or "{}"

    if _debug:
        _log.info("dismiss stdin: %s", stdin_raw[:100])

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = _extract_session_id(data, None)
    count = dismiss_session(session_id or "", debug=debug)

    if _debug:
        _log.info(
            "dismiss: session_id=%s, marked=%d", session_id[:8] if session_id else "NONE", count
        )


def handle_register(session_id: str | None = None, cwd: str | None = None) -> bool:
    """Register/update an OpenClaw session with the current TTY.

    Designed to be run from within OpenClaw's TUI via the ! prefix:
        !lemonaid openclaw register

    If session_id is provided, registers that specific session.
    Otherwise, finds the most recently modified session.

    Returns True if successful, False otherwise.
    """
    # Get TTY - should inherit from TUI process
    tty = get_tty()

    _log.info("register: session_id=%s, tty=%s", session_id, tty)

    if not tty:
        print("Warning: Could not detect TTY. Notification will use cwd-based matching.")

    # Find session - either by ID or most recent
    if session_id:
        session_path = find_session_path(session_id)
        if session_path:
            header = read_session_header(session_path)
            agent_id = session_path.parent.parent.name if session_path else None
            session_cwd = header.get("cwd") if header else None
        else:
            session_path, agent_id, session_cwd = None, None, None
    else:
        session_path, session_id, agent_id, session_cwd = find_most_recent_session()

    if not session_path or not session_id:
        if session_id:
            print(f"Session not found: {session_id}")
        else:
            print("No OpenClaw session found")
        _log.info("no session found")
        return False

    _log.info("found session: %s, agent=%s, cwd=%s", session_id[:8], agent_id, session_cwd)

    # Use session's cwd (from header), not the TUI's working directory
    cwd = session_cwd or cwd or os.getcwd()

    # Build metadata
    switch_source = detect_terminal_switch_source()
    # Get session name: label > session key segment > cwd folder name
    name = None
    if agent_id:
        name = get_session_name(agent_id, session_id)
    if not name:
        name = get_name_from_cwd(cwd)
    short_path = shorten_path(cwd)
    message = f"Registered in {short_path}"

    metadata: dict[str, str] = {
        "cwd": cwd,
        "session_id": session_id,
        "session_path": str(session_path),
    }
    if agent_id:
        metadata["agent_id"] = agent_id
        session_key = get_session_key(agent_id, session_id)
        if session_key:
            metadata["session_key"] = session_key
    if tty:
        metadata["tty"] = tty

    channel = f"openclaw:{session_id[:8]}"

    # Upsert the notification
    with db.connect() as conn:
        existing = db.get_by_channel(conn, channel, unread_only=False)

        if existing:
            # Update existing - preserve message but update TTY
            new_metadata = {**existing.metadata, **metadata}
            # Keep the existing message unless it's the default "Registered" message
            if not existing.message.startswith("Registered"):
                message = existing.message

            db.add(
                conn,
                channel=channel,
                message=message,
                name=existing.name or name,
                metadata=new_metadata,
                switch_source=switch_source
                if switch_source != "unknown"
                else existing.switch_source,
            )
            action = "updated"
        else:
            db.add(
                conn,
                channel=channel,
                message=message,
                name=name,
                metadata=metadata,
                switch_source=switch_source if switch_source != "unknown" else None,
            )
            action = "created"

    # Get session info for confirmation
    session_name = None
    if agent_id:
        session_name = get_session_name(agent_id, session_id)
    last_message = get_last_user_message(session_path)

    # Print confirmation with enough info to verify correct session
    tty_display = tty.replace("/dev/", "") if tty else "none"
    print(f"Registered most recent session (tty: {tty_display})")
    print(f"  Channel: {channel}")
    print(f"  Cwd: {cwd}")
    if session_name:
        print(f"  Name: {session_name}")
    if last_message:
        print(f"  Last input: {last_message}")
    print()
    print("If this is the wrong session, use: lemonaid openclaw register --session-id <id>")

    _log.info("%s: %s, tty=%s", action, channel, tty)

    return True
