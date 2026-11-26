"""A receiver its harness starts itself, with no pane to replace it in (OpenClaw's).

A sender in a tmux pane is stopped first, so the brief never has two live lemons: its harness
process is terminated and confirmed gone, as recovery does, and the pane's shell is replaced
by a placeholder only once nothing else runs on its terminal. The placeholder's process id
stands in as the target's, so that a start that fails
before any receiver exists resumes the sender there, as a failed pane replacement does. Once a
receiver may be running, a failure leaves the handoff incomplete with the sender's resume
command instead: an ambiguous failure must not start a second harness.
"""

import shlex
import sqlite3
from collections import abc

from ...config import load_config
from ...launch.restart import pane, planning, process
from ...launch.restart import state as restart_state
from ...watch import registry, stopping
from . import state

Start = abc.Callable[[sqlite3.Connection, sqlite3.Row, abc.Callable[[str], None]], None]


def _placeholder(row: sqlite3.Row) -> str:
    resume = f"cd {row['resume_cwd']} && {row['resume_line']}" if row["resume_line"] else ""
    return " ".join(
        part
        for part in (
            f"This lemon handed its brief to {row['harness']} (handoff {row['token']}).",
            f"`lemonaid brief handoff status {row['token']}` shows how it went.",
            f"The old session resumes with: {resume}" if resume else "",
        )
        if part
    )


def _launched(conn: sqlite3.Connection, token: str, channel: str) -> None:
    conn.execute("UPDATE brief_handoffs SET phase = 'launched' WHERE token = ?", (token,))
    conn.commit()
    if not state.bind_target(conn, token, channel):
        raise ValueError(f"Could not reserve {channel} as the handoff's receiver")


def _stop_sender(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    """Terminate the sender's harness, put the placeholder in its pane, and return the
    placeholder's process id. Raises ValueError, OSError or TimeoutError."""
    plan = planning.build(conn, row["source"], load_config(), force=True)
    target = pane.Pane(**plan["pane"])
    if (target.pane, target.window) != (row["source_pane_id"], row["source_window_id"]):
        raise ValueError("The outgoing harness is no longer in the handoff's pane")

    pane.preserve(target)
    process.terminate(process.Identity(**plan["source"]))
    for waiter in registry.mine(row["source"]):
        stopping.stop(waiter, f"handoff {row['token']}")
    held = pane.replace(
        target,
        process.Identity(**plan["root"]),
        plan["cwd"],
        f"printf '%s\\n' {shlex.quote(_placeholder(row))}; exec tail -f /dev/null",
        {},
    )
    pane.restore(held, plan["exit_option"])
    return str(held.pid)


def start(conn: sqlite3.Connection, row: sqlite3.Row, start_receiver: Start) -> None:
    """Stop a sender in a pane, then start the receiver. Raises ValueError, OSError or
    TimeoutError."""
    token = row["token"]
    if row["source_pane_id"] and not row["target_pid"]:
        with restart_state.barrier(row["source"], exclusive=True):
            held = _stop_sender(conn, row)
        conn.execute(
            "UPDATE brief_handoffs SET phase = 'prepared', target_pid = ? WHERE token = ?",
            (held, token),
        )
        conn.commit()
    start_receiver(conn, state.get(conn, token), lambda channel: _launched(conn, token, channel))


def unresumed(row: sqlite3.Row, reason: str) -> str:
    """Why the handoff stopped without resuming its sender, once a receiver may be running;
    "" while none can be, when the sender may be resumed."""
    if not row["target"]:
        return ""

    resume = (
        f"; resume it with: cd {row['resume_cwd']} && {row['resume_line']}"
        if row["resume_line"]
        else ""
    )
    return (
        f"handoff {reason}; receiver {row['target']} may be running, so the outgoing session"
        f" was not resumed{resume}"
    )
