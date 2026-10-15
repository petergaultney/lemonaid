"""Detached, journaled cutover. No destructive step is replayed after a crash."""

import fcntl
import os
import sqlite3
import subprocess
import sys
import typing as ty
from pathlib import Path

from ...brief import attached
from ...inbox import db
from ...watch import registry, stopping
from . import (
    configuration,
    environment,
    history,
    jobs,
    native,
    pane,
    planning,
    process,
    startup,
    state,
    watchers,
)


def _recheck(conn: sqlite3.Connection, plan: dict[str, ty.Any]) -> None:
    target = pane.Pane(**plan["pane"])
    pane.check(target)
    if not process.same(process.Identity(**plan["source"])):
        raise ValueError("Source process generation changed")

    allowed = {entry.pid for entry in process.ancestry(plan["source"]["pid"])} | {
        entry["pid"] for entry in plan.get("caller", []) if process.same(process.Identity(**entry))
    }
    allowed |= {entry.pid for entry in process.ancestry(os.getpid())} | jobs.saved(plan)
    if any(
        entry.pid not in allowed
        for entry in [*process.on_tty(target.tty), *process.descendants(plan["source"]["pid"])]
    ):
        raise ValueError("Unmanaged terminal or descendant jobs appeared after preflight")

    row = db.get_by_channel(conn, plan["channel"], unread_only=False)
    if row is None or attached.by_channel(conn, [plan["channel"]]).get(plan["channel"]) is None:
        raise ValueError("Source row or brief attachment disappeared")
    if (
        row.metadata.get("session_id") != plan["session_id"]
        or row.metadata.get("cwd") != plan["cwd"]
    ):
        raise ValueError("Source session identity or directory changed")

    generation = native.registered(conn, plan["channel"])
    if (
        generation is None
        or generation["identity"] != plan["source"]
        or generation["settings"] != plan["settings"]
    ):
        raise ValueError("Native identity or effective settings changed after preflight")

    pane.model(target, plan["settings"]["model"], str(plan["settings"].get("effort") or ""))
    configuration.unchanged(plan["settings"].get("files", {}))
    planning.idle(row, plan["lemon_id"], plan["force"])
    history.validate(Path(plan["history"]), plan["session_id"], plan["harness"], plan["force"])
    stamp = Path(plan["history"]).stat()
    if not plan["force"] and [stamp.st_size, stamp.st_mtime_ns] != plan["history_stamp"]:
        raise ValueError("Native transcript changed after preflight; retry when idle")
    if not plan["force"]:
        pane.composer(target, plan["harness"])


def _execute(conn: sqlite3.Connection, operation: dict[str, ty.Any]) -> None:
    token, plan = operation["token"], operation["plan"]
    target = pane.Pane(**plan["pane"])
    environment.validate(plan["settings"])
    waiters = registry.mine(plan["channel"])
    watchers.check_source(plan["harness"], waiters)
    state.update(conn, token, "quiescing")
    for waiter in waiters:
        stopping.stop(waiter, f"restart {token}")
    _recheck(conn, plan)
    pane.preserve(target)
    state.update(conn, token, "stopping")
    process.terminate(process.Identity(**plan["source"]))
    state.update(conn, token, "source-exited")
    startup.run(conn, token)


def reconcile(conn: sqlite3.Connection, operation: dict[str, ty.Any], error: str) -> None:
    """Release a failed reservation without signaling or launching another harness."""
    plan, evidence = operation["plan"], operation["evidence"]
    original = process.Identity(**plan["source"])
    outcome = "failed" if process.same(original) else "partial"
    target = pane.Pane(**evidence.get("replacement", plan["pane"]))
    try:
        if operation["phase"] != "planned" and (
            process.same(original)
            or (
                evidence.get("replacement_root")
                and process.same(process.Identity(**evidence["replacement_root"]))
            )
        ):
            pane.restore(target, plan["exit_option"])
    except (ValueError, OSError, subprocess.TimeoutExpired) as restore_error:
        error += f"; pane option: {restore_error}"
    state.update(conn, operation["token"], outcome, error=error)
    if process.same(original) and operation["phase"] != "planned":
        try:
            watchers.restore(plan)
        except (OSError, TimeoutError, ValueError) as restore_error:
            state.update(conn, operation["token"], outcome, error=f"{error}; {restore_error}")


def run(token: str) -> None:
    lock_path = db.get_db_path().parent / f"restart-coordinator-{token}.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return

        with db.connect() as conn:
            operation = state.get(conn, token)
            if operation["phase"] in state.TERMINAL:
                return
            if operation["phase"] != "planned":
                reconcile(
                    conn, operation, "Coordinator interrupted; inspect the saved recovery command"
                )
                return

            try:
                _execute(conn, operation)
            except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
                reconcile(conn, state.get(conn, token), str(error))


def spawn(token: str) -> None:
    log = db.get_db_path().parent / f"restart-{token}.log"
    with log.open("a") as output:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid.launch.restart.worker", token],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
            close_fds=True,
            env={**os.environ, "LEMONAID_DB": str(db.get_db_path())},
        )
