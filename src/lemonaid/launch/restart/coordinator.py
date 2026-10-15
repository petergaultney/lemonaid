"""One detached stop/start; native resume owns session restoration."""

import contextlib
import dataclasses
import fcntl
import json
import subprocess
import sys
import time

from ...config import load_config
from ...inbox import db
from ...watch import registry, stopping
from . import native, pane, planning, process, state


def _execute(token: str, plan: dict) -> None:
    with db.connect() as conn:
        current = planning.build(conn, plan["channel"], load_config(), plan["force"])
        if any(
            current[k] != plan[k] for k in ("source", "pane", "line", "environment", "lemon_id")
        ):
            raise ValueError(
                "The process, pane, attachment or resume command changed after preflight"
            )
        if conn.execute(
            "SELECT 1 FROM brief_handoffs WHERE source = ? AND phase NOT IN ('complete','failed')",
            (plan["channel"],),
        ).fetchone():
            raise ValueError("A handoff is in progress")
    target = pane.Pane(**plan["pane"])
    pane.preserve(target)
    state.update(token, "stopping")
    process.terminate(process.Identity(**plan["source"]))
    # Let the harness close its own tools. Do not classify or kill helper processes.
    # Stop its registered delivery processes before reusing the terminal.
    for waiter in registry.mine(plan["channel"]):
        stopping.stop(waiter, f"restart {token}")
    state.update(token, "starting")
    replacement = pane.replace(
        target, process.Identity(**plan["root"]), plan["cwd"], plan["line"], plan["environment"]
    )
    if pane.check(replacement).dead:
        raise ValueError(
            "Resume command exited; inspect the retained pane and saved resume command"
        )
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = json_patch(metadata, ?) WHERE channel = ?",
            (json.dumps({"tty": replacement.tty}), plan["channel"]),
        )
        conn.commit()
    state.update(token, "starting", replacement=dataclasses.asdict(replacement))
    # A fresh process observation prevents autoresume racing native CLI startup.
    # This checks ownership only; settings, tools and watcher readiness belong to the harness.
    deadline = time.monotonic() + 15
    while not native.resumed(plan["channel"], plan["source"], replacement.pid):
        if pane.check(replacement).dead or time.monotonic() >= deadline:
            raise TimeoutError("Resume process did not register; inspect the retained pane")
        time.sleep(0.1)
    pane.restore(replacement, plan["exit_option"])
    state.update(token, "started", replacement=dataclasses.asdict(replacement))


def run(token: str) -> None:
    operation = state.get(token)
    with state._path(token + ".lock").open("a+") as lock:
        # Starting a worker and admitting competing work share the channel barrier.
        with state.barrier(operation["plan"]["channel"], exclusive=True):
            operation = state.get(token)
            if operation["phase"] != "planned":
                return  # Never repeat an uncertain stop or respawn.
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
        plan = operation["plan"]
        try:
            _execute(token, plan)
        except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
            source_alive = process.same(process.Identity(**plan["source"]))
            if source_alive and state.get(token)["phase"] != "planned":
                with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
                    pane.restore(pane.Pane(**plan["pane"]), plan["exit_option"])
            state.update(token, "failed" if source_alive else "partial", error=str(error))


def spawn(token: str) -> None:
    with state._path(token + ".log").open("a") as log:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid.launch.restart.worker", token],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
