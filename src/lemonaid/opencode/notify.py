"""OpenCode notification hook handler."""

import json
import os
import sys

from ..inbox import db
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_git_branch,
    get_name_from_cwd,
    get_tty,
    shorten_path,
)
from ..log import get_logger
from .utils import get_cwd_and_name

_log = get_logger("opencode.notify")


def _channel_for_session(session_id: str | None) -> str:
    if not session_id:
        return "opencode:unknown"
    return f"opencode:{session_id}"


def _extract_session_id(data: dict[str, object]) -> str | None:
    keys = (
        "session_id",
        "sessionId",
        "sessionID",
        "id",
    )
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    props_obj = data.get("properties")
    props: dict[str, object] = props_obj if isinstance(props_obj, dict) else {}
    for key in keys:
        value = props.get(key)
        if isinstance(value, str) and value:
            return value

    session_raw = data.get("session")
    session_obj: dict[str, object] = session_raw if isinstance(session_raw, dict) else {}
    for key in keys:
        value = session_obj.get(key)
        if isinstance(value, str) and value:
            return value

    props_session_raw = props.get("session")
    props_session: dict[str, object] = (
        props_session_raw if isinstance(props_session_raw, dict) else {}
    )
    for key in keys:
        value = props_session.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _default_message(notification_type: str, cwd: str | None) -> str:
    short_path = shorten_path(cwd) if cwd else "OpenCode"
    if "permission" in notification_type:
        return f"Permission needed in {short_path}"
    if notification_type == "session.idle":
        return f"Waiting in {short_path}"
    return f"{notification_type} in {short_path}"


def handle_notification(
    stdin_data: str | None = None,
    *,
    session_id: str | None = None,
    cwd: str | None = None,
    name: str | None = None,
    message: str | None = None,
    notification_type: str | None = None,
) -> None:
    """Handle an OpenCode notification from stdin or explicit args."""
    if stdin_data is None:
        stdin_data = sys.stdin.read() if not sys.stdin.isatty() else ""
    stdin_data = stdin_data or ""

    _log.info("stdin: %s", stdin_data[:200])

    try:
        loaded = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        loaded = {}

    data: dict[str, object] = loaded if isinstance(loaded, dict) else {}

    data_type = data.get("type")
    data_event = data.get("event")
    if not notification_type:
        if isinstance(data_type, str) and data_type:
            notification_type = data_type
        elif isinstance(data_event, str) and data_event:
            notification_type = data_event
        else:
            notification_type = "session.idle"
    session_id = session_id or _extract_session_id(data)

    if session_id and (not cwd or not name):
        discovered_cwd, discovered_name = get_cwd_and_name(session_id)
        cwd = cwd or discovered_cwd
        name = name or discovered_name

    if not cwd:
        directory = data.get("directory")
        cwd_value = data.get("cwd")
        cwd = (
            directory
            if isinstance(directory, str)
            else cwd_value
            if isinstance(cwd_value, str)
            else None
        )
    if not name:
        title = data.get("title")
        data_name = data.get("name")
        name = (
            title
            if isinstance(title, str)
            else data_name
            if isinstance(data_name, str)
            else get_name_from_cwd(cwd or "")
        )

    message = message or _default_message(notification_type, cwd)

    switch_source = detect_terminal_switch_source()
    metadata: dict[str, str] = {}
    if cwd:
        metadata["cwd"] = cwd
    if session_id:
        metadata["session_id"] = session_id
    metadata["notification_type"] = notification_type

    branch = get_git_branch(cwd or "")
    if branch:
        metadata["git_branch"] = branch

    tty = get_tty()
    if tty:
        metadata["tty"] = tty

    channel = _channel_for_session(session_id)

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


def _dismiss_session(session_id: str, debug: bool = False) -> int:
    """Dismiss (mark as read) the notification for an OpenCode session."""
    if not session_id:
        if debug:
            print("[dismiss] no session_id provided", file=sys.stderr)
        return 0

    channel = _channel_for_session(session_id)
    with db.connect() as conn:
        count = db.mark_all_read_for_channel(conn, channel)
        # Backward compatibility for notifications created with legacy short channel ids
        legacy_channel = f"opencode:{session_id[:8]}"
        if legacy_channel != channel:
            count += db.mark_all_read_for_channel(conn, legacy_channel)
        if debug:
            print(
                f"[dismiss] marked {count} notification(s) as read for {channel}",
                file=sys.stderr,
            )
        return count


def handle_dismiss(debug: bool = False) -> None:
    """Dismiss (mark as read) the notification for this OpenCode session."""
    debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"

    stdin_raw = (sys.stdin.read() if not sys.stdin.isatty() else "{}") or "{}"

    _log.info("dismiss stdin: %s", stdin_raw[:100])

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = _extract_session_id(data)
    count = _dismiss_session(session_id or "", debug=debug)

    _log.info("dismiss: session_id=%s, marked=%d", session_id[:8] if session_id else "NONE", count)
