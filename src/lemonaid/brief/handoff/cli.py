"""Coordinate a sequential harness handoff in the same pane or terminal."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time

from ...inbox import db
from ...inbox.channel import channel_id, full_channel_id
from .. import attached, lemon
from . import coordinator as handoff_coordinator
from . import pane as handoff_tmux
from . import request
from . import shell as handoff_shell
from . import state as handoff_state


def _cmd(args: argparse.Namespace) -> None:
    if args.watch:
        lock = db.get_db_path().parent / f"handoff-{args.token}.lock"
        with lock.open("w") as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return

            stop_sent_at = 0.0
            while True:
                try:
                    with db.connect() as conn:
                        row = handoff_state.get(conn, args.token)
                        report = handoff_coordinator.advance(conn, args.token)
                    if getattr(args, "source_pid", 0) and report["phase"] == "launched":
                        now = time.time()
                        if not stop_sent_at:
                            if handoff_shell.stop_job_if_same(
                                args.source_pid,
                                args.source_pgid,
                                args.source_tty,
                                args.source_start,
                            ):
                                stop_sent_at = now
                        elif now - stop_sent_at > 3:
                            handoff_shell.stop_job_if_same(
                                args.source_pid,
                                args.source_pgid,
                                args.source_tty,
                                args.source_start,
                                force=True,
                            )
                    if (
                        report["phase"] in ("complete", "failed")
                        or time.time() > row["deadline"]
                        or row["error"]
                    ):
                        return
                except (ValueError, OSError, subprocess.SubprocessError):
                    with db.connect() as conn:
                        try:
                            row = handoff_state.get(conn, args.token)
                        except ValueError:
                            return

                        handoff_coordinator.recover_source(conn, row, "failed")
                    return

                time.sleep(1)

    direct_tty = False
    token = ""
    try:
        with db.connect() as conn:
            if getattr(args, "recover", False) and (
                not args.to
                or not getattr(args, "yes", False)
                or not (getattr(args, "source", "") or getattr(args, "brief", ""))
            ):
                raise ValueError("Recovery needs --to, an explicit --source or --brief, and --yes")
            if args.to:
                token, direct_tty, source_job = request.prepare(
                    conn,
                    args.to,
                    args.brief,
                    getattr(args, "source", ""),
                    getattr(args, "recover", False),
                )
            else:
                token, source_job = args.token, None

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
                    if not row["target_pane_id"]:
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
                request.watch(token, source_job)

        if direct_tty:
            handoff_shell.launch_from_tty(token, source_job)
            return
        print(json.dumps(report))
    except (ValueError, LookupError, OSError, subprocess.SubprocessError) as error:
        if args.to and token:
            with db.connect() as conn:
                handoff_coordinator.recover_source(conn, handoff_state.get(conn, token), "failed")
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("handoff", help="Move this brief to another harness")
    parser.add_argument("action", nargs="?", choices=("status", "ready", "accept"))
    parser.add_argument("token", nargs="?", default="")
    parser.add_argument(
        "--to", metavar="NAME", help="Claude, Codex, or a named lemon running either backend"
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--brief", default="", help="Outgoing brief path or Lemon-ID")
    selector.add_argument("--source", default="", help="Outgoing full Lemon-ID or unique name half")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Use saved context in the same pane; stop the verified source without an outgoing turn",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Confirm recovery using existing durable context"
    )
    parser.add_argument("--source-pid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--source-pgid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--source-tty", default="", help=argparse.SUPPRESS)
    parser.add_argument("--source-start", default="", help=argparse.SUPPRESS)
    parser.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(func=_cmd)
