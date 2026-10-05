"""Advance a tokened handoff while keeping tmux layout checks at the edge."""

import json
import time
from pathlib import Path

from ..inbox import db
from . import attached, handoff_codex, handoff_launch, handoff_state, handoff_tmux, handoff_transfer


def source(conn, channel: str, harness: str) -> tuple[Path, str, str, str, str, str]:
    path = attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        raise ValueError("No brief is attached to this lemon")

    row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None or row.status == "archived":
        raise ValueError("The outgoing channel has no live inbox row")

    session = str(row.metadata.get("tmux_session") or "")
    index = str(row.metadata.get("tmux_window") or "")
    pane, window_id = handoff_tmux.pane(session, index) if session and index else ("", "")
    if not pane:
        raise ValueError("The outgoing lemon needs one live pane in a tmux window")

    current_command = handoff_tmux.current_command(pane)
    if not current_command:
        raise ValueError("Could not inspect the outgoing pane's command")

    if channel.startswith(harness + ":"):
        raise ValueError("The destination harness is already running this brief")

    return path, session, index, window_id, pane, current_command


def _target_channel(conn, row) -> str:
    found = []
    for item in conn.execute(
        "SELECT channel, metadata FROM notifications WHERE status != 'archived'"
    ):
        metadata = json.loads(item["metadata"] or "{}")
        if (
            metadata.get("tmux_session") == row["session"]
            and str(metadata.get("tmux_window")) == row["target_window"]
            and item["channel"] != row["source"]
            and item["channel"].startswith(row["harness"] + ":")
        ):
            found.append(item["channel"])

    return found[0] if len(set(found)) == 1 else ""


def advance(conn, token: str) -> dict:
    row = handoff_state.get(conn, token)
    if row["phase"] in ("complete", "failed"):
        return _report(row)

    if row["phase"] == "transferred":
        if not handoff_tmux.close_old(row):
            return {**_report(row), "missing": ["old pane changed; close its window by hand"]}

        conn.execute("UPDATE brief_handoffs SET phase = 'complete' WHERE token = ?", (token,))
        conn.commit()
        return _report(handoff_state.get(conn, token))

    if time.time() > row["deadline"]:
        return {**_report(row), "missing": ["deadline passed; retry with --to to extend it"]}

    if (
        handoff_tmux.pane(row["session"], row["source_window"])
        != (row["source_pane_id"], row["source_window_id"])
        and row["phase"] != "transferred"
    ):
        return {**_report(row), "missing": ["outgoing pane changed; cutover stopped"]}

    if row["phase"] == "requested":
        handoff_codex.phrases(conn, row)
        good, reason = handoff_state.ready(conn, row)
        if not good:
            return {**_report(row), "missing": [reason]}

        handoff_state.acknowledge(conn, token, row["source"], "ready")
        handoff_launch.run(conn, row)
        row = handoff_state.get(conn, token)

    if row["phase"] == "prepared":
        handoff_launch.run(conn, row)
        row = handoff_state.get(conn, token)

    if row["phase"] == "launched":
        if handoff_tmux.pane(row["session"], row["target_window"]) != (
            row["target_pane_id"],
            row["target_window_id"],
        ):
            return {**_report(row), "missing": ["new pane changed; cutover stopped"]}

        target = row["target"] or _target_channel(conn, row)
        if target and not row["target"]:
            conn.execute("UPDATE brief_handoffs SET target = ? WHERE token = ?", (target, token))
            conn.commit()
            row = handoff_state.get(conn, token)

        handoff_codex.phrases(conn, row)
        row = handoff_state.get(conn, token)

        if not target or not row["accepted"]:
            return {**_report(row), "missing": ["new channel or accept acknowledgement"]}

        notification = db.get_by_channel(conn, target, unread_only=False)
        if notification is None or notification.status == "archived":
            return {**_report(row), "missing": ["new channel has not registered an inbox row"]}

        if attached.by_channel(conn, [target]):
            return {**_report(row), "missing": ["new channel already has another brief"]}

        handoff_transfer.transfer(conn, token)
        row = handoff_state.get(conn, token)
        return advance(conn, token)

    return _report(row)


def _report(row) -> dict:
    return {
        "token": row["token"],
        "phase": row["phase"],
        "source": row["source"],
        "target": row["target"] or None,
        "old_window": f"{row['session']}:{row['source_window']}",
        "new_window": f"{row['session']}:{row['target_window']}" if row["target_window"] else None,
        "ready_phrase": f"lemonaid handoff ready {row['token']}",
        "accept_phrase": f"lemonaid handoff accept {row['token']}",
        "missing": [],
    }
