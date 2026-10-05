"""Advance a tokened handoff while keeping tmux layout checks at the edge."""

import fcntl
import hashlib
import time
from pathlib import Path

from ..inbox import db
from . import (
    attached,
    handoff_codex,
    handoff_launch,
    handoff_report,
    handoff_state,
    handoff_tmux,
    handoff_transfer,
)


def source(conn, channel: str, harness: str) -> tuple[Path, str, str, str, str, str]:
    path = attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        raise ValueError("No brief is attached to this lemon")

    row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None or row.status == "archived":
        raise ValueError("The outgoing channel has no live inbox row")

    session = str(row.metadata.get("tmux_session") or "")
    index = str(row.metadata.get("tmux_window") or "")
    tty = str(row.metadata.get("tty") or "")
    pane, window_id = (
        handoff_tmux.pane_for_tty(session, index, tty)
        if session and index and tty
        else handoff_tmux.pane(session, index)
        if session and index
        else ("", "")
    )
    current_command = (
        handoff_tmux.current_command(pane) if pane else str(row.metadata.get("cwd") or "")
    )
    if pane and not current_command:
        raise ValueError("Could not inspect the outgoing pane's command")
    if not pane and (not current_command or not Path(current_command).is_dir()):
        raise ValueError("The outgoing lemon's working directory is unavailable")

    if channel.startswith(harness + ":"):
        raise ValueError("The destination harness is already running this brief")

    return path, session, index, window_id, pane, current_command


def recover_source(conn, row, reason: str) -> str:
    if row["error"]:
        return row["error"]

    if not row["source_pane_id"]:
        error = (
            f"handoff {reason}; outgoing channel retains its brief; "
            "resume the original session if it exited, then rearm its waiters before retrying"
        )
    elif row["target_pid"]:
        resumed = handoff_tmux.resume_source(conn, row)
        error = (
            f"handoff {reason}; outgoing session resumed in its original pane"
            if resumed
            else f"handoff {reason}; could not safely resume the outgoing session; "
            "check the pane and resume its original session manually"
        )
        if resumed and row["remain_on_exit"]:
            handoff_tmux.set_remain_on_exit(row["source_pane_id"], row["remain_on_exit"])
    elif (
        row["phase"] == "prepared"
        and (state := handoff_tmux.pane_process(row["source_pane_id"], row["source_window_id"]))
        and state[0] != row["source_pid"]
    ):
        error = (
            f"handoff {reason}; pane process changed before its identity was saved; "
            "inspect the pane and resume the original session manually"
        )
    elif row["source"].startswith("claude:"):
        error = (
            f"handoff {reason}; outgoing Claude was prompted to rearm its waiter"
            if handoff_tmux.prompt_source_to_rearm(row, reason)
            else f"handoff {reason}; rearm the outgoing Claude waiter before retrying"
        )
    else:
        error = f"handoff {reason}; outgoing session remains active"
    if row["phase"] == "prepared" and row["remain_on_exit"] and not row["target_pid"]:
        state = handoff_tmux.pane_process(row["source_pane_id"], row["source_window_id"])
        if state and state[0] == row["source_pid"]:
            handoff_tmux.set_remain_on_exit(row["source_pane_id"], row["remain_on_exit"])
    conn.execute(
        "UPDATE brief_handoffs SET phase = 'failed', error = ? WHERE token = ?",
        (error, row["token"]),
    )
    conn.commit()
    return error


def _advance(conn, token: str) -> dict:
    row = handoff_state.get(conn, token)
    if row["phase"] in ("complete", "failed"):
        return handoff_report.build(row)

    if row["phase"] == "transferred":
        if row["source_pane_id"] and row["remain_on_exit"]:
            state = handoff_tmux.pane_process(row["target_pane_id"], row["target_window_id"])
            if state is None or state != (row["target_pid"], False):
                return {
                    **handoff_report.build(row),
                    "missing": ["replacement pane changed; inspect its exit setting"],
                }
            if not handoff_tmux.set_remain_on_exit(row["source_pane_id"], row["remain_on_exit"]):
                return {
                    **handoff_report.build(row),
                    "missing": ["could not restore the pane exit setting"],
                }

        conn.execute("UPDATE brief_handoffs SET phase = 'complete' WHERE token = ?", (token,))
        conn.commit()
        return handoff_report.build(handoff_state.get(conn, token))

    if time.time() > row["deadline"]:
        error = recover_source(conn, row, "timed out")
        return {
            **handoff_report.build(handoff_state.get(conn, token)),
            "missing": [error + "; start a new handoff with --to after recovery"],
        }

    if row["error"]:
        return {
            **handoff_report.build(row),
            "missing": [row["error"] + "; start a new handoff with --to after recovery"],
        }

    if (
        row["source_pane_id"]
        and row["phase"] == "requested"
        and not handoff_tmux.has_pane(row["source_pane_id"], row["source_window_id"])
    ):
        return {**handoff_report.build(row), "missing": ["outgoing pane changed; cutover stopped"]}

    if row["phase"] == "requested":
        handoff_codex.phrases(conn, row)
        good, reason = handoff_state.ready(conn, row)
        if not good:
            return {**handoff_report.build(row), "missing": [reason]}

        handoff_state.acknowledge(conn, token, row["source"], "ready")
        if not row["source_pane_id"]:
            conn.execute("UPDATE brief_handoffs SET phase = 'launched' WHERE token = ?", (token,))
            conn.commit()
            return {
                **handoff_report.build(handoff_state.get(conn, token)),
                "missing": ["start the target command, then accept from that harness"],
            }
        handoff_launch.run(conn, row)
        row = handoff_state.get(conn, token)

    if row["phase"] == "prepared":
        handoff_launch.run(conn, row)
        row = handoff_state.get(conn, token)

    if row["phase"] == "launched":
        if row["source_pane_id"]:
            state = handoff_tmux.pane_process(row["target_pane_id"], row["target_window_id"])
            if state is None or state[0] != row["target_pid"]:
                return {
                    **handoff_report.build(row),
                    "missing": ["replacement pane changed; cutover stopped"],
                }
            if state[1]:
                error = recover_source(conn, row, "target exited")
                return {**handoff_report.build(handoff_state.get(conn, token)), "missing": [error]}

        # Native harness notifications bind the token to their real session ID.
        # A pane's TTY can be reused by an older live row, so it is not identity.
        target = row["target"]

        if row["source_pane_id"]:
            handoff_codex.phrases(conn, row)
        row = handoff_state.get(conn, token)

        if not target or not row["accepted"]:
            return {
                **handoff_report.build(row),
                "missing": ["new channel or accept acknowledgement"],
            }

        notification = db.get_by_channel(conn, target, unread_only=False)
        if notification is None or notification.status == "archived":
            return {
                **handoff_report.build(row),
                "missing": ["new channel has not registered an inbox row"],
            }

        if attached.by_channel(conn, [target]):
            return {
                **handoff_report.build(row),
                "missing": ["new channel already has another brief"],
            }

        handoff_transfer.transfer(conn, token)
        row = handoff_state.get(conn, token)
        return _advance(conn, token)

    return handoff_report.build(row)


def advance(conn, token: str) -> dict:
    key = hashlib.sha256(token.encode()).hexdigest()
    lock = db.get_db_path().parent / f"handoff-advance-{key}.lock"
    with lock.open("w") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        return _advance(conn, token)
