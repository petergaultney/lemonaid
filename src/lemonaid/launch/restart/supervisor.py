"""A second detached process releases reservations if the coordinator dies."""

import subprocess
import sys

from ...inbox import db
from . import coordinator, state


def monitor(token: str, child: subprocess.Popen) -> None:
    try:
        child.wait(timeout=100)
    except subprocess.TimeoutExpired:
        # This PID is our own child, never a process discovered on the terminal.
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    with db.connect() as conn:
        operation = state.get(conn, token)
        if operation["phase"] not in state.TERMINAL:
            coordinator.reconcile(
                conn, operation, "Coordinator exited before completion; inspect this operation"
            )


def run(token: str) -> None:
    child = subprocess.Popen(
        [sys.executable, "-m", "lemonaid.launch.restart.worker", token, "--coordinate"]
    )
    monitor(token, child)
