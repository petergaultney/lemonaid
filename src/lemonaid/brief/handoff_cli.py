"""Coordinate a sequential harness handoff in the same pane or terminal."""

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import time

from ..config import load_config
from ..inbox import db
from ..inbox.channel import channel_id, full_channel_id
from ..messages import to_brief
from ..resume import build_resume_command
from . import (
    attached,
    handoff_coordinator,
    handoff_launch,
    handoff_state,
    handoff_tmux,
    lemon,
    store,
)

_DEADLINE_SECONDS = 600


def _cmd(args: argparse.Namespace) -> None:
    if args.watch:
        lock = db.get_db_path().parent / f"handoff-{args.token}.lock"
        with lock.open("w") as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return

            while True:
                try:
                    with db.connect() as conn:
                        row = handoff_state.get(conn, args.token)
                        report = handoff_coordinator.advance(conn, args.token)
                    if (
                        report["phase"] in ("complete", "failed")
                        or time.time() > row["deadline"]
                        or row["error"]
                    ):
                        return
                except (ValueError, OSError):
                    with db.connect() as conn:
                        try:
                            row = handoff_state.get(conn, args.token)
                        except ValueError:
                            return

                        handoff_coordinator.recover_source(conn, row, "failed")
                    return

                time.sleep(1)

    try:
        with db.connect() as conn:
            if args.to:
                if args.brief:
                    path = store.resolve(args.brief)
                    if store.outside_error(path):
                        raise ValueError(store.outside_error(path))
                    holders = [
                        item.channel for item in attached.everything(conn) if item.path == path
                    ]
                    if len(holders) != 1 or not holders[0]:
                        raise ValueError("The brief needs one attached outgoing channel")
                    channel = holders[0]
                else:
                    channel = lemon.self_channel(conn)
                path, session, index, window_id, pane_id, source_command = (
                    handoff_coordinator.source(conn, channel, args.to)
                )
                notification = db.get_by_channel(conn, channel, unread_only=False)
                resume = build_resume_command(load_config(), channel, notification.metadata)
                if resume is None or not resume[1]:
                    raise ValueError("The outgoing session has no usable resume command")
                existing = conn.execute(
                    "SELECT * FROM brief_handoffs WHERE path = ? AND phase NOT IN ('complete', 'failed')",
                    (str(path),),
                ).fetchone()
                row = handoff_state.request(
                    conn,
                    path,
                    channel,
                    args.to,
                    session,
                    index,
                    window_id,
                    pane_id,
                    source_command,
                    time.time() + _DEADLINE_SECONDS,
                )
                conn.execute(
                    "UPDATE brief_handoffs SET resume_line = ?, resume_cwd = ? WHERE token = ?",
                    (shlex.join(resume[1]), resume[0], row["token"]),
                )
                conn.commit()
                row = handoff_state.get(conn, row["token"])
                handoff_launch.reserve_source(conn, row)
                row = handoff_state.get(conn, row["token"])
                if existing is None or existing["error"] or time.time() > existing["deadline"]:
                    to_brief.send(
                        path,
                        "Write a fresh ## Handoff with at most five bullets. Do not reread files "
                        "when the brief is already current. Stop your waiters. Put "
                        f"Handoff-Ready: {row['token']} on its own final line in the brief. "
                        "You may instead print that exact line in your final reply after editing "
                        "## Handoff. Once ready, exit your harness normally so its shell returns; "
                        "lemonaid will start the replacement in this pane. Do not stop the pane or shell.",
                    )
                token = row["token"]
            else:
                token = args.token

            if args.action in ("ready", "accept"):
                channel = lemon.self_channel(conn)
                if args.action == "accept":
                    handoff_coordinator.advance(conn, token)
                    row = handoff_state.get(conn, token)
                    session_id = (
                        os.environ.get("CODEX_THREAD_ID", "")
                        if row["harness"] == "codex"
                        else os.environ.get("CLAUDE_CODE_SESSION_ID", "")
                    )
                    real_channel = (
                        (
                            full_channel_id("codex", session_id)
                            if row["harness"] == "codex"
                            else channel_id("claude", session_id)
                        )
                        if session_id
                        else ""
                    )
                    if (
                        row["phase"] != "launched"
                        or row["error"]
                        or channel != real_channel
                        or channel == row["source"]
                        or os.environ.get("LEMONAID_HANDOFF_TOKEN", "") not in ("", token)
                    ):
                        raise ValueError("Accept needs the launched target harness and its token")
                    if not row["source_pane_id"]:
                        if attached.by_channel(conn, [channel]):
                            raise ValueError("The target channel already has a brief")
                        handoff_state.bind_target(conn, token, channel)
                    else:
                        pane = os.environ.get("TMUX_PANE", "")
                        state = handoff_tmux.pane_process(
                            row["target_pane_id"], row["target_window_id"]
                        )
                        if (
                            pane != row["target_pane_id"]
                            or os.environ.get("LEMONAID_HANDOFF_TOKEN") != token
                            or state is None
                            or state != (row["target_pid"], False)
                        ):
                            raise ValueError("Accept came from another pane or process")
                        if attached.by_channel(conn, [channel]):
                            raise ValueError("The target channel already has a brief")
                        handoff_state.bind_target(conn, token, channel)

                handoff_state.acknowledge(conn, token, channel, args.action)

            report = handoff_coordinator.advance(conn, token)
            if report["phase"] != "complete":
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "lemonaid",
                        "brief",
                        "handoff",
                        "status",
                        token,
                        "--watch",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=os.environ.copy(),
                )
        print(json.dumps(report))
    except (ValueError, LookupError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("handoff", help="Move this brief to another harness")
    parser.add_argument("action", nargs="?", choices=("status", "ready", "accept"))
    parser.add_argument("token", nargs="?", default="")
    parser.add_argument("--to", choices=("claude", "codex"))
    parser.add_argument("--brief", default="", help="Outgoing brief, if called by another lemon")
    parser.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(func=_cmd)
