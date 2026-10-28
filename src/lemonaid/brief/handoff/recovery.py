"""Replace a verified outgoing process using its saved brief instead of a final turn."""

import os
import shlex
import sqlite3
import subprocess
from pathlib import Path

from ...config import load_config
from ...launch import command
from ...launch.restart import pane, planning, process, state
from ...watch import registry, stopping
from .. import check
from . import launch as handoff_launch
from . import pane as handoff_tmux


def _plan(conn: sqlite3.Connection, channel: str, pane_id: str, window_id: str) -> dict:
    plan = planning.build(conn, channel, load_config(), force=True)
    target = pane.Pane(**plan["pane"])
    if (target.pane, target.window) != (pane_id, window_id) or handoff_tmux.pane_process(
        pane_id, window_id
    ) != (str(target.pid), False):
        raise ValueError("The native process and outgoing handoff pane disagree")
    source = process.Identity(**plan["source"])
    if source in process.ancestry(os.getpid()):
        raise ValueError(
            "Request Recovery from the inbox or another terminal, outside the outgoing harness"
        )

    return plan


def validate(
    conn: sqlite3.Connection, path: Path, session: str, pane_id: str, channel: str, window_id: str
) -> None:
    if not session or not pane_id:
        raise ValueError("Recovery needs an identifiable live tmux source pane")
    text = path.read_text()
    if problems := [*check.structure(text), *check.recorded(conn, path, text)]:
        raise ValueError("brief check failed: " + "; ".join(problems))
    _plan(conn, channel, pane_id, window_id)


def _launch(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    if row["phase"] != "requested":
        raise ValueError("Recovery launch interrupted; inspect its pane before retrying")
    line = handoff_launch.configured_line(row["launch_name"] or row["harness"])
    shlex.split(line)
    if error := command.unclaimable(line):
        raise ValueError(error)
    plan = _plan(conn, row["source"], row["source_pane_id"], row["source_window_id"])
    target = pane.Pane(**plan["pane"])
    source = process.Identity(**plan["source"])
    previous = handoff_tmux.remain_on_exit(target.pane)
    if previous not in ("on", "off", "failed"):
        raise ValueError("Could not inspect the outgoing pane's exit behavior")
    prompt = (
        f"This is a confirmed recovery without a final outgoing turn. Read {row['path']} "
        "as the existing durable context; it may be incomplete. Do not assume ## Handoff is fresh. "
        f"Run lemonaid brief handoff accept {row['token']}, then rearm your brief's watches "
        "and continue its task. The outgoing process was stopped; this is its original pane."
    )
    typed, environment = command.harness_line(
        line, Path(plan["cwd"]), prompt, command.codex_writable_roots(load_config().tmux_session)
    )
    pane.preserve(target)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'prepared', source_pid = ?,
           target_pane_id = ?, target_window_id = ?, target_window = ?, remain_on_exit = ?
           WHERE token = ?""",
        (str(target.pid), target.pane, target.window, row["source_window"], previous, row["token"]),
    )
    conn.commit()
    try:
        process.terminate(source)
        for waiter in registry.mine(row["source"]):
            stopping.stop(waiter, f"handoff {row['token']}")
        replacement = pane.replace(
            target,
            process.Identity(**plan["root"]),
            plan["cwd"],
            typed,
            {**environment, "LEMONAID_HANDOFF_TOKEN": row["token"]},
        )
        if (
            replacement.pane != target.pane
            or replacement.window != target.window
            or replacement.pid == target.pid
        ):
            raise ValueError("Could not verify replacement in the original pane")
    except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
        if process.same(source):
            pane.restore(target, plan["exit_option"])
            conn.execute(
                "UPDATE brief_handoffs SET phase = 'failed', error = ? WHERE token = ?",
                (str(error), row["token"]),
            )
            conn.commit()
        raise
    conn.execute(
        "UPDATE brief_handoffs SET phase = 'launched', target_pid = ? WHERE token = ?",
        (str(replacement.pid), row["token"]),
    )
    conn.commit()


def launch(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    with state.barrier(row["source"], exclusive=True):
        _launch(conn, row)
