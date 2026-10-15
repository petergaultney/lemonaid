"""Reconcile abandoned leases without replaying signals or uncertain launches."""

import fcntl
import sqlite3
import subprocess
import time
import typing as ty

from ...inbox import db
from ...log import get_logger
from . import pane, process

_log = get_logger("restart.expiry")


def reconcile(conn: sqlite3.Connection, operation: dict[str, ty.Any]) -> bool:
    if operation["deadline"] > time.time():
        return False

    path = db.get_db_path().parent / f"restart-coordinator-{operation['token']}.lock"
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False

        error = "Restart lease expired without a coordinator; inspect the pane and rearm its watcher. No launch was replayed."
        plan, evidence = operation["plan"], operation["evidence"]
        try:
            original = process.same(process.Identity(**plan["source"]))
            replacement = evidence.get("replacement_root")
            if original or (replacement and process.same(process.Identity(**replacement))):
                target = pane.Pane(**evidence.get("replacement", plan["pane"]))
                pane.restore(target, plan["exit_option"])
        except (OSError, ValueError, subprocess.TimeoutExpired) as restore_error:
            error += f" {restore_error}"
        conn.execute(
            "UPDATE lemon_restarts SET phase = 'partial', error = ? WHERE token = ?",
            (error, operation["token"]),
        )
        conn.commit()
        _log.warning("%s: %s", operation["token"], error)
        return True
