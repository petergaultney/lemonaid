"""Codex CLI notification hook handler."""

import json
import os
import sys
import time
from pathlib import Path

from .. import auto_read, messages
from ..brief.handoff import state as handoff_state
from ..brief.handoff import transfer as handoff_transfer
from ..config import load_config
from ..inbox import db
from ..inbox.channel import UnidentifiedSession, full_channel_id
from ..launch.restart import native
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_git_branch,
    get_name_from_cwd,
    shorten_path,
)
from ..log import get_logger
from . import channels, location, permissions, thread_name, threads, turns
from .utils import extract_session_id_from_filename

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


def _extract_session_id(data: dict) -> str | None:
    # Codex's generic `id` identifies the notification/turn, not the thread.
    for key in ("session_id", "sessionId", "thread_id", "thread-id", "threadId"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value

    return None


def _codex_thread(
    session_id: str | None, cwd: str | None, session_path: str | None
) -> threads.Thread | None:
    """Codex's record of the hook's thread, or None when Codex doesn't know it or can't
    be asked."""
    thread = session_id or extract_session_id_from_filename(Path(session_path or "").name)
    if thread:
        answers = threads.get([thread], running=True)
        if thread not in answers:
            _log.warning("Codex could not be asked about thread %s", thread)
        return answers.get(thread)

    return threads.latest_in(cwd) if cwd else None


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
    payload_session_id = _extract_session_id(data)
    thread = _codex_thread(session_id or payload_session_id, resolved_cwd, session_path)
    if thread is None:
        _log.info(
            "ignored a thread Codex doesn't know: thread=%s", session_id or payload_session_id
        )
        return

    if thread.parent:
        _log.info("ignored a spawned thread: thread=%s parent=%s", thread.id, thread.parent)
        return

    known = thread
    session_id = session_id or known.id
    native.observe({"session_id": session_id}, "codex")
    cwd = resolved_cwd or known.cwd
    notification_type = (
        notification_type
        or data.get("notification_type")
        or data.get("event")
        or data.get("hook_event_name")
        or data.get("type")
        or "agent-turn-complete"
    )

    if (
        notification_type == "PermissionRequest"
        and known.path
        and permissions.automatically_reviewed(
            Path(known.path), data.get("turn_id", ""), data.get("tool_name", "")
        )
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
    if known.path:
        metadata["session_path"] = known.path
    thread_id = data.get("thread_id") or data.get("thread-id") or data.get("threadId")
    if isinstance(thread_id, str) and thread_id:
        metadata["thread_id"] = thread_id
    branch = get_git_branch(cwd or "")
    if branch:
        metadata["git_branch"] = branch

    metadata.update(location.pane_metadata(switch_source))

    try:
        channel = full_channel_id("codex", session_id)
    except UnidentifiedSession:
        _log.warning("dropped a notification with no session id: cwd=%s", cwd)
        return

    # Add to inbox (upsert=True by default, so repeated notifications update timestamp)
    turn = data.get("turn-id") or data.get("turn_id")
    turn = turn if isinstance(turn, str) else ""
    ends_turn = notification_type in _TURN_ENDED
    with db.connect() as conn:
        if not os.environ.get("LEMONAID_HANDOFF_TOKEN"):
            channel = channels.channel(session_id or "")
        if ends_turn:
            conn.execute("BEGIN IMMEDIATE")  # no turn hook writes between the check and add
            if turns.superseded(db.get_by_channel(conn, channel, unread_only=False), turn):
                db.record_turn_end(conn, channel, turn, time.time(), interrupted=False)
                _log.info("kept a later turn: channel=%s ended=%s", channel, turn)
                return

        db.add(
            conn,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
            status=_status_after(notification_type, channel, data),
            ends_turn=ends_turn,
        )
        if ends_turn:
            db.record_turn_end(conn, channel, turn, time.time(), interrupted=False)
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
        channel = channels.channel(session_id)
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

    session_id = _extract_session_id(data)
    count = dismiss_session(session_id or "", debug=debug)

    _log.info("dismiss: session_id=%s, marked=%d", session_id[:8] if session_id else "NONE", count)


def handle_turn_hook(stdin_data: str | None = None) -> None:
    """Record a turn's start, tool use or interrupt, and clear a permission notice whose
    requested tool has started or returned. A turn's start also names its thread."""
    if stdin_data is None:
        stdin_data = sys.stdin.read()

    try:
        data = json.loads(stdin_data) if stdin_data else {}
    except json.JSONDecodeError:
        data = {}

    turns.record(data)
    _clear_permission_notice(data)
    if data.get("hook_event_name") == "UserPromptSubmit" and (thread := _extract_session_id(data)):
        thread_name.push(thread)


def _clear_permission_notice(data: dict) -> None:
    session_id = _extract_session_id(data)
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
        channel = channels.channel(session_id)
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
