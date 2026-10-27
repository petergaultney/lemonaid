"""Record a Codex session in the inbox when it starts, from Codex's SessionStart hook.

Codex's notify hook only fires when a turn ends, and a lemon's first turn can
run for many minutes. Until a row says which pane a thread is in, nothing can
claim the brief waiting on that window, and `doctor` and `brief children` call
the lemon dead.
"""

import os
from pathlib import Path

from ..brief.handoff import state as handoff_state
from ..brief.handoff import transfer as handoff_transfer
from ..inbox import db
from ..inbox.channel import full_channel_id
from ..lemon_watchers import (
    detect_terminal_switch_source,
    get_git_branch,
    get_name_from_cwd,
    shorten_path,
)
from ..log import get_logger
from . import channels, location
from .utils import find_session_path, is_spawned_thread, read_session_meta

_log = get_logger("codex.startup")


def _rollout(data: dict, session_id: str) -> Path | None:
    given = data.get("transcript_path")
    if isinstance(given, str) and given and Path(given).is_file():
        return Path(given)

    return find_session_path(session_id)


def register(data: dict) -> None:
    """Register the hook's thread as a working (read) row, unless it is a subagent's."""
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return

    rollout = _rollout(data, session_id)
    meta = read_session_meta(rollout) if rollout else None
    if meta is None or is_spawned_thread(meta):
        _log.info("not registering thread %s: no rollout, or a spawned thread", session_id)
        return

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else meta.get("cwd") or ""
    switch_source = detect_terminal_switch_source()
    metadata = {
        "cwd": cwd,
        "session_id": session_id,
        "session_path": str(rollout),
        "notification_type": "SessionStart",
        "session_start_source": data.get("source") or "startup",
        "name_source": "environment",
        **({"git_branch": branch} if (branch := get_git_branch(cwd)) else {}),
        **location.pane_metadata(switch_source),
    }
    with db.connect() as conn:
        token = os.environ.get("LEMONAID_HANDOFF_TOKEN")
        channel = (
            full_channel_id("codex", session_id)
            if token
            else channels.for_session(conn, session_id)
        )
        db.register_working(
            conn,
            channel=channel,
            message=f"Started in {shorten_path(cwd)}",
            name=get_name_from_cwd(cwd),
            metadata=metadata,
            switch_source=switch_source if switch_source != "unknown" else None,
        )
        if token:
            handoff_state.bind_target(conn, token, channel)
        handoff_transfer.reclaim(conn, channel)

    _log.info(
        "session start: channel=%s tmux=%s:%s",
        channel,
        metadata.get("tmux_session"),
        metadata.get("tmux_window"),
    )
