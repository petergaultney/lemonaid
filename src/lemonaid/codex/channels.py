"""Keep transient Codex notification IDs on the attached lemon's channel."""

import sqlite3
from typing import Any

from ..inbox import db
from . import utils


def _matches(row: db.Notification, thread: str, location: dict[str, Any]) -> bool:
    recorded = row.channel.removeprefix("codex:")
    if recorded == thread:
        return True
    canonical = row.metadata.get("session_id")
    rollout = utils.extract_session_id_from_filename(row.metadata.get("session_path", ""))
    # A reconciled alias belongs to its root, even after another root takes its pane.
    if canonical and canonical == rollout and canonical != recorded and canonical != thread:
        return False
    same_rollout = rollout == thread
    same_location = bool(
        row.metadata.get("tmux_pane_identity") == location.get("tmux_pane_identity")
        and row.metadata.get("tty") == location.get("tty")
        and row.metadata.get("tmux_socket") == location.get("tmux_socket")
        and row.metadata.get("cwd")
        and (not location.get("cwd") or row.metadata["cwd"] == location["cwd"])
    )
    if not (same_rollout or same_location):
        return False
    # Real sessions on the same pane can be a /clear or a restart.
    return utils.find_session_path(recorded) is None


def _attached_rows(conn: sqlite3.Connection) -> list[db.Notification]:
    return [
        db.Notification.from_row(row)
        for row in conn.execute(
            "SELECT n.* FROM notifications n JOIN session_briefs b ON b.channel = n.channel "
            "WHERE n.switch_source = 'tmux' AND n.channel LIKE 'codex:%' "
            "AND n.id = (SELECT MAX(id) FROM notifications WHERE channel = b.channel)"
        )
    ]


def attached_channel(conn: sqlite3.Connection, thread: str, location: dict[str, Any]) -> str | None:
    rows = _attached_rows(conn)
    exact = [row.channel for row in rows if row.channel == f"codex:{thread}"]
    if exact:
        return exact[0]
    protected = _handoff_channels(conn)
    if f"codex:{thread}" in protected:
        return None
    matches = {
        row.channel
        for row in rows
        if row.channel not in protected and _matches(row, thread, location)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _handoff_channels(conn: sqlite3.Connection) -> set[str]:
    """Leave both ends alone until the explicit transfer has finished or failed."""
    return {
        channel
        for row in conn.execute(
            "SELECT h.source, h.target, b.channel FROM brief_handoffs h "
            "LEFT JOIN session_briefs b ON b.path = h.path "
            "WHERE h.phase NOT IN ('complete', 'failed')"
        )
        for channel in row
        if channel
    }


def repair_duplicates(conn: sqlite3.Connection, locations: dict[str, list[dict[str, Any]]]) -> int:
    attached = {row["channel"] for row in conn.execute("SELECT channel FROM session_briefs")}
    protected = _handoff_channels(conn)
    rows = [
        *db.get_active(conn, switch_source="tmux"),
        *(row for row in db.get_snoozed(conn) if row.switch_source == "tmux"),
    ]
    repaired = 0
    for thread, matches in locations.items():
        if len(matches) != 1 or not (target := attached_channel(conn, thread, matches[0])):
            continue
        if target in protected:
            continue
        current = db.get_by_channel(conn, target, unread_only=False)
        path = utils.find_session_path(thread)
        if current is not None and path is not None:
            db.repair_location(conn, current, {"session_id": thread, "session_path": str(path)})
        for row in rows:
            if not row.channel.startswith("codex:") or row.channel in attached | protected:
                continue
            if not _matches(row, thread, matches[0]):
                continue
            if row.is_unread:
                current = db.get_by_channel(conn, target, unread_only=False)
                if current and current.status == "read":
                    db.mark_unread(conn, current.id)
            db.archive_channel(conn, row.channel, "codex-duplicate-notification-channel")
            repaired += 1
    return repaired


def for_session(conn: sqlite3.Connection, thread: str) -> str:
    channel = f"codex:{thread}"
    attached = {row["channel"] for row in conn.execute("SELECT channel FROM session_briefs")}
    if channel in attached:
        return channel
    matches = [
        row.channel
        for row in _attached_rows(conn)
        if row.channel in attached
        and row.channel.startswith("codex:")
        and row.metadata.get("session_id") == thread
        and utils.extract_session_id_from_filename(row.metadata.get("session_path", "")) == thread
        and utils.find_session_path(row.channel.removeprefix("codex:")) is None
    ]
    return matches[0] if len(matches) == 1 else channel


def owner_id(
    channel: str, metadata: dict[str, Any], locations: dict[str, list[dict[str, Any]]]
) -> str:
    recorded = channel.removeprefix("codex:")
    if recorded in locations:
        return recorded
    owner = metadata.get("session_id")
    if owner and utils.extract_session_id_from_filename(metadata.get("session_path", "")) == owner:
        return owner
    return recorded
