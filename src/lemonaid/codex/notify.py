"""Codex CLI notification hook handler."""

import json
import os
import sys
import time
from pathlib import Path

from .. import auto_read, messages
from ..brief import handoff_state, handoff_transfer
from ..config import load_config
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, full_channel_id
from ..launch.restart import native
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_cmux_surface,
    get_git_branch,
    get_name_from_cwd,
    get_tmux_pane_tty,
    get_tmux_session_name,
    get_tmux_session_order,
    get_tmux_socket,
    get_tty,
    shorten_path,
)
from ..log import get_logger
from . import channels, hosting, permissions
from .utils import (
    extract_session_id_from_filename,
    find_latest_session_for_cwd,
    find_session_path,
    is_spawned_thread,
    read_session_meta,
)

_log = get_logger("codex.notify")


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
    # Codex's generic `id` identifies the notification/turn, not the rollout.
    # Treating it as a session ID leaves the watcher looking for a file that
    # cannot exist.
    for key in ("session_id", "sessionId", "thread_id", "thread-id", "threadId"):
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
    if session_id:
        return find_session_path(session_id)

    if session_path:
        path = Path(session_path).expanduser()
        if path.exists():
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


_TURN_ENDED = ("agent-turn-complete", "turn-complete", "idle_prompt")


def _status_after(notification_type: str, channel: str, data: dict) -> str:
    """Unread, or read when a finished turn's final message matches `[inbox] auto_read`."""
    if notification_type not in _TURN_ENDED:
        return "unread"

    said = data.get("last-assistant-message") or data.get("last_assistant_message")
    return auto_read.status_after_turn(
        load_config().inbox.auto_read, channel, said if isinstance(said, str) else ""
    )


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
    if stdin_data is None:
        stdin_data = sys.stdin.read()
        # Codex notify passes a single JSON argument, not stdin.
        if not stdin_data.strip() and len(sys.argv) > 1 and sys.argv[-1].lstrip().startswith("{"):
            stdin_data = sys.argv[-1]

    _log.info("stdin: %s", stdin_data[:200])

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    data_cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    resolved_cwd = cwd or data_cwd
    payload_session_id = _extract_session_id(data, None)
    session_path_obj = _resolve_session_path(
        session_id or payload_session_id, resolved_cwd, session_path
    )
    if session_path_obj is None:
        _log.info("ignored a thread with no rollout: thread=%s", session_id or payload_session_id)
        return
    meta = read_session_meta(session_path_obj)
    if meta is None:
        # Codex writes session_meta when a thread starts, so this is a damaged
        # rollout - and possibly a subagent's, which must not get a row.
        _log.warning("ignored a thread whose rollout has no session_meta: %s", session_path_obj)
        return

    if meta and is_spawned_thread(meta):
        _log.info(
            "ignored a spawned thread: thread=%s parent=%s source=%s",
            meta.get("id"),
            meta.get("parent_thread_id"),
            meta.get("thread_source"),
        )
        return

    canonical_session_id = _extract_session_id({}, session_path_obj)
    session_id = session_id or canonical_session_id or payload_session_id
    native.observe({"session_id": session_id}, "codex")
    cwd = _resolve_cwd(resolved_cwd, session_path_obj)
    notification_type = (
        notification_type
        or data.get("notification_type")
        or data.get("event")
        or data.get("hook_event_name")
        or data.get("type")
        or "agent-turn-complete"
    )

    if notification_type == "PermissionRequest" and permissions.automatically_reviewed(
        session_path_obj, data.get("turn_id", ""), data.get("tool_name", "")
    ):
        _log.info(
            "ignored automatic approval review: session=%s turn=%s", session_id, data.get("turn_id")
        )
        return

    if not message:
        short_path = shorten_path(cwd or "")
        if "approval" in notification_type.lower() or "permission" in notification_type.lower():
            message = f"Permission needed in {short_path}"
        elif notification_type in _TURN_ENDED:
            message = f"Waiting in {short_path}"
        else:
            message = f"{notification_type} in {short_path}"

    name = name or data.get("name") or data.get("customTitle") or data.get("title")
    name_source = "codex_title" if name else "environment"
    if not name:
        name = _parse_input_messages(data) or get_name_from_cwd(cwd or "")

    # Detect switch-source (which terminal environment this notification came from)
    switch_source = detect_terminal_switch_source()

    # Build metadata for handler
    metadata: dict[str, str | list[int]] = {}
    if cwd:
        metadata["cwd"] = cwd
    if session_id:
        metadata["session_id"] = session_id
    if notification_type:
        metadata["notification_type"] = notification_type
    for key in ("tool_name", "turn_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            metadata[key] = value
    metadata["name_source"] = name_source
    if session_path_obj:
        metadata["session_path"] = str(session_path_obj)
    thread_id = data.get("thread_id") or data.get("thread-id") or data.get("threadId")
    if isinstance(thread_id, str) and thread_id:
        metadata["thread_id"] = thread_id
    branch = get_git_branch(cwd or "")
    if branch:
        metadata["git_branch"] = branch

    # Under the app-server daemon, the tty found is the daemon's, not this
    # session's pane; recording it would put every Codex session in one pane.
    hosted = hosting.under_app_server()
    tty = None if hosted else get_tty()
    if not tty and not hosted and switch_source == "tmux":
        tty = get_tmux_pane_tty()
    if tty:
        metadata["tty"] = tty
        surface = get_cmux_surface()
        if surface:
            metadata["cmux_surface"] = surface

    # This hook runs in the session's own pane (except app-server hooks, which
    # have no session TTY). Record the tmux session identity so a later TTY
    # reuse cannot make another Codex session look like this one.
    if tty and switch_source == "tmux":
        if tmux_session := get_tmux_session_name():
            metadata["tmux_session"] = tmux_session
        if socket := get_tmux_socket():
            metadata["tmux_socket"] = socket
        if session_order := get_tmux_session_order():
            metadata["tmux_session_order"] = list(session_order)
            if pane := os.environ.get("TMUX_PANE"):
                metadata["tmux_pane_identity"] = [pane, session_order[1]]

    try:
        channel = full_channel_id("codex", session_id)
    except UnidentifiedSession:
        _log.warning("dropped a notification with no session id: cwd=%s", cwd)
        return

    # Add to inbox (upsert=True by default, so repeated notifications update timestamp)
    with db.connect() as conn:
        if not os.environ.get("LEMONAID_HANDOFF_TOKEN"):
            channel = channels.for_session(conn, session_id or "")
        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
            status=_status_after(notification_type, channel, data),
            ends_turn=notification_type in _TURN_ENDED,
        )
        if token := os.environ.get("LEMONAID_HANDOFF_TOKEN"):
            handoff_state.bind_target(conn, token, channel)
        handoff_transfer.reclaim(conn, channel)
        pending = messages.service.has_pending(conn, channel)

    _log.info(
        "added: channel=%s, type=%s payload_thread=%s owner_thread=%s",
        channel,
        notification_type,
        payload_session_id,
        session_id,
    )
    if pending:
        messages.service.ensure_running()  # messages that waited while this lemon was archived


def dismiss_session(session_id: str, debug: bool = False) -> int:
    """Dismiss (mark as read) the notification for a Codex session."""
    if not session_id:
        if debug:
            print("[dismiss] no session_id provided", file=sys.stderr)
        return 0

    channel = full_channel_id("codex", session_id)
    with db.connect() as conn:
        channel = channels.for_session(conn, session_id)
        count = db.mark_all_read_for_channel(conn, channel)
        if debug:
            print(
                f"[dismiss] marked {count} notification(s) as read for {channel}", file=sys.stderr
            )
        return count


def handle_dismiss(debug: bool = False) -> None:
    """Dismiss (mark as read) the notification for this Codex session."""
    debug = debug or os.environ.get("LEMONAID_DEBUG") == "1"

    stdin_raw = sys.stdin.read() or "{}"

    _log.info("dismiss stdin: %s", stdin_raw[:100])

    try:
        data = json.loads(stdin_raw)
    except json.JSONDecodeError:
        data = {}

    session_id = _extract_session_id(data, None)
    count = dismiss_session(session_id or "", debug=debug)

    _log.info("dismiss: session_id=%s, marked=%d", session_id[:8] if session_id else "NONE", count)


def handle_tool_used(stdin_data: str | None = None) -> None:
    """Clear a matching permission notice when Codex starts or finishes the requested tool."""
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    session_id = _extract_session_id(data, None)
    tool_name = data.get("tool_name")
    turn_id = data.get("turn_id")
    if (
        not session_id
        or not isinstance(tool_name, str)
        or not tool_name
        or not isinstance(turn_id, str)
        or not turn_id
    ):
        return

    channel = full_channel_id("codex", session_id)
    with db.connect() as conn:
        channel = channels.for_session(conn, session_id)
        row = conn.execute(
            "SELECT id, metadata FROM notifications WHERE channel = ?", (channel,)
        ).fetchone()
        if not row:
            return

        try:
            metadata = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            return

        if (
            metadata.get("notification_type") != "PermissionRequest"
            or metadata.get("tool_name") != tool_name
            or metadata.get("turn_id") != turn_id
        ):
            return

        cursor = conn.execute(
            "UPDATE notifications SET status = 'read', read_at = ?, message = ?"
            " WHERE id = ? AND metadata = ? AND status IN ('unread', 'read')",
            (time.time(), f"Using {tool_name}", row["id"], row["metadata"]),
        )
        conn.commit()

    if cursor.rowcount:
        _log.info(
            "cleared permission notice after tool use: channel=%s tool=%s", channel, tool_name
        )
