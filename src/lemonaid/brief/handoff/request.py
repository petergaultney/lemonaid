"""Request a cooperative handoff or confirmed recovery from shared CLI and UI callers."""

import os
import shlex
import sqlite3
import subprocess
import sys
import time

from ...config import load_config
from ...inbox import db
from ...messages import to_brief
from ...resume import build_resume_command
from .. import lemon
from . import coordinator, launch, recovery, selection, shell, state


def _pending_handoff(conn, path, now: float):
    """Return a live same-brief handoff, retiring expired or errored attempts."""
    existing = conn.execute(
        "SELECT * FROM brief_handoffs WHERE path = ? AND phase NOT IN ('complete', 'failed')",
        (str(path),),
    ).fetchone()
    if existing is None:
        return None
    if existing["recovery_hash"] and existing["phase"] == "prepared":
        raise ValueError(
            f"Recovery {existing['token']} may have replaced its source; inspect its pane before retrying"
        )
    if existing["error"] or existing["deadline"] <= now:
        error = existing["error"] or "Expired handoff superseded by a new request"
        conn.execute(
            "UPDATE brief_handoffs SET phase = 'failed', error = ? WHERE token = ?",
            (error, existing["token"]),
        )
        conn.commit()
        return None
    return existing


def _request_message(channel: str, token: str, same_terminal: bool) -> str:
    exit_instruction = (
        "After writing the ready marker, exit this harness normally so the "
        "same terminal can start the replacement. "
        if same_terminal
        else ""
    )
    sandbox_instruction = (
        "If Codex blocks writing this brief or running `lemonaid brief check`, "
        "retry those operations with escalated permissions before reporting ready. "
        if channel.startswith("codex:")
        else ""
    )
    return (
        "Write a fresh ## Handoff with at most five bullets. Do not reread files "
        "when the brief is already current. Stop your waiters. "
        f"Put Handoff-Ready: {token} on its own final line in the brief. "
        "You may instead print that exact line in your final reply after editing "
        f"## Handoff. {sandbox_instruction}{exit_instruction}"
        "The old session stays active until cutover."
    )


def prepare(
    conn: sqlite3.Connection,
    destination: str,
    brief: str = "",
    source: str = "",
    recover: bool = False,
) -> tuple[str, bool, tuple | None]:
    source_job = None
    backend = launch.destination(destination)
    on_tty = not (brief or source) and sys.stdin.isatty()
    stopped = None
    if on_tty:
        tty = os.ttyname(sys.stdin.fileno())
        stopped = shell.stopped_harness_on_tty(tty, shell.harnesses_on_tty(conn, tty))
    direct_tty = bool(on_tty and (stopped or not os.environ.get("TMUX_PANE")))
    same_terminal = direct_tty
    if source or brief:
        channel = selection.channel(conn, source, brief)
    elif direct_tty:
        tty = os.ttyname(sys.stdin.fileno())
        channel = shell.channel_on_tty(conn, tty)
        source_harness = channel.split(":", 1)[0]
        if stopped is None:
            source_job = shell.stopped_job_on_tty(tty, source_harness)
        elif stopped[0] != source_harness:
            raise ValueError(
                f"Found stopped {stopped[0]} on {tty}, but attached session "
                f"{channel} is {source_harness}; refusing to guess which one to hand off."
            )
        else:
            source_job = stopped[1]
    else:
        channel = lemon.self_channel(conn)
    path, session, index, window_id, pane_id, source_command = coordinator.source(conn, channel)
    notification = db.get_by_channel(conn, channel, unread_only=False)
    if same_terminal:
        shlex.split(launch.configured_line(destination, destination))
        tty = os.ttyname(sys.stdin.fileno())
        if notification.metadata.get("tty") != tty:
            raise ValueError("The outgoing harness was recorded on another terminal")
        pane_id, window_id = "", ""
        source_command = str(notification.metadata.get("cwd") or "")
        if not os.path.isdir(source_command):
            raise ValueError("The outgoing lemon's working directory is unavailable")
    resume = build_resume_command(load_config(), channel, notification.metadata)
    if resume is None or not resume[1]:
        raise ValueError("The outgoing session has no usable resume command")
    if same_terminal or recover:
        existing = _pending_handoff(conn, path, time.time())
    else:
        existing = conn.execute(
            "SELECT * FROM brief_handoffs WHERE path = ? AND phase NOT IN ('complete', 'failed')",
            (str(path),),
        ).fetchone()
    if existing is not None and bool(existing["recovery_hash"]) != recover:
        raise ValueError("A different handoff mode is pending for this brief")
    if existing is not None and same_terminal:
        raise ValueError("A handoff is already pending for this brief")
    if recover:
        if existing is not None:
            raise ValueError("A handoff is pending; resolve it before recovery")
        recovery.validate(conn, path, session, pane_id, channel, window_id)
    row = state.request(
        conn,
        path,
        channel,
        backend,
        session,
        index,
        window_id,
        pane_id,
        source_command,
        time.time() + 600,
        launch_name=destination,
        recovery_hash=state.digest(path.read_text()) if recover else "",
    )
    conn.execute(
        "UPDATE brief_handoffs SET resume_line = ?, resume_cwd = ? WHERE token = ?",
        (shlex.join(resume[1]), resume[0], row["token"]),
    )
    conn.commit()
    row = state.get(conn, row["token"])
    if not row["recovery_hash"] and (
        existing is None or existing["error"] or time.time() > existing["deadline"]
    ):
        to_brief.send(path, _request_message(channel, row["token"], same_terminal))
    token = row["token"]
    return token, direct_tty, source_job


def watch(token: str, source_job: tuple | None = None) -> None:
    watcher_args = [
        sys.executable,
        "-m",
        "lemonaid",
        "brief",
        "handoff",
        "status",
        token,
        "--watch",
    ]
    if source_job:
        watcher_args.extend(
            (
                "--source-pid",
                str(source_job[0]),
                "--source-pgid",
                str(source_job[1]),
                "--source-tty",
                source_job[2],
                "--source-start",
                source_job[3],
            )
        )
    subprocess.Popen(
        watcher_args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ.copy(),
    )
