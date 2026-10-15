"""Preflight is read-only with respect to the target harness and its watchers."""

import dataclasses
import os
import sqlite3
import time
import typing as ty
from pathlib import Path

from ...brief import identity, lemon
from ...claude import launch_args, session_socket
from ...config import Config
from ...inbox import db
from ...messages import recipient, store
from ...watch import registry
from . import configuration, history, native, pane, process, settings


def idle(row: db.Notification, lemon_id: str, force: bool) -> None:
    found = recipient.probe(row.channel, row, store.inbox_for_id(lemon_id))
    if found.state in (recipient.DEAD, recipient.UNKNOWN, recipient.NOT_STARTED):
        raise ValueError(f"{found.state}: use lemon resume for an exited harness")
    if (row.asks or found.state in (recipient.MID_TURN, recipient.ASKING)) and not force:
        raise ValueError("The lemon is mid-turn or asking for input; use --force to interrupt it")


def build(
    conn: sqlite3.Connection, target: str, config: Config, force: bool = False
) -> dict[str, ty.Any]:
    attachment = lemon.attachment(conn, target, claim_pending=False)
    row = attachment.notification
    if row is None or row.is_archived:
        raise ValueError("The lemon has no live row; use lemon resume")

    harness = row.channel.partition(":")[0]
    if harness not in ("claude", "codex"):
        raise ValueError("Only Claude and dedicated Codex terminals support restart")

    lemon_id = identity.from_path(attachment.path)
    idle(row, lemon_id, force)
    cwd = str(row.metadata.get("cwd") or "")
    if not cwd or not Path(cwd).is_dir():
        raise ValueError("The recorded working directory is gone")

    target_pane = pane.locate(
        str(row.metadata.get("tmux_socket") or ""), str(row.metadata.get("tty") or "")
    )
    if target_pane.dead or target_pane.cwd != cwd:
        raise ValueError("The live pane and recorded working directory disagree")

    session = str(row.metadata.get("session_id") or "")
    if not session or len(session) < 16:
        raise ValueError("The full native session ID is unavailable")

    generation = native.registered(conn, row.channel)
    if generation is None:
        raise ValueError(
            "No native process binding; install hooks and start a dedicated session first"
        )
    if generation["session_id"] != session:
        raise ValueError("Native process binding belongs to a different session")

    source = process.Identity(**generation["identity"])
    root = process.inspect(target_pane.pid)
    lineage = process.ancestry(source.pid)
    if (
        root is None
        or not process.same(source)
        or root not in lineage
        or source.tty != target_pane.tty.removeprefix("/dev/")
    ):
        raise ValueError("Native session process is not the recorded pane's harness generation")

    argv = launch_args.argv(source.pid)
    if harness == "codex" and ("--no-daemon" not in argv or "app-server" in argv):
        raise ValueError("Shared Codex app-server processes cannot be restarted")

    history_path = row.metadata.get("session_path") or row.metadata.get("transcript_path")
    if harness == "claude" and not history_path:
        paths = list((session_socket.claude_dir() / "projects").glob(f"*/{session}.jsonl"))
        history_path = str(paths[0]) if len(paths) == 1 else ""
    if not history_path or not Path(history_path).is_file():
        raise ValueError("The exact native session history is unavailable")

    history.validate(Path(history_path), session, harness, force)

    effective = generation["settings"]
    if effective.get("error"):
        raise ValueError(effective["error"])

    command = settings.command(row, config, effective)
    configuration.unchanged(effective.get("files", {}))
    pane.model(target_pane, effective["model"])
    waiters = registry.mine(row.channel)
    caller = process.ancestry(os.getpid())
    own_chain = caller[: caller.index(source)] if source in caller else []
    allowed = {e.pid for e in lineage} | {e.pid for e in own_chain} | {w.pid for w in waiters}
    unknown = [p for p in process.on_tty(target_pane.tty) if p.pid not in allowed]
    if unknown:
        raise ValueError(f"Unmanaged jobs on the terminal: {[p.pid for p in unknown]}")
    if not force:
        pane.composer(target_pane, harness)

    stat = Path(history_path).stat()
    return {
        "channel": row.channel,
        "lemon_id": lemon_id,
        "session_id": session,
        "harness": harness,
        "cwd": cwd,
        "pane": dataclasses.asdict(target_pane),
        "source": dataclasses.asdict(source),
        "root": dataclasses.asdict(root),
        "caller": [dataclasses.asdict(entry) for entry in own_chain],
        "settings": effective,
        "argv": command,
        "force": force,
        "history": str(history_path),
        "history_stamp": [stat.st_size, stat.st_mtime_ns],
        "waiters": [dataclasses.asdict(w) for w in waiters],
        "planned_at": time.time(),
        "exit_option": pane.exit_option(target_pane),
    }
