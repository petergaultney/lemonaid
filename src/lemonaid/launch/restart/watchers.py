"""Rebuild watcher processes while retaining declarations and delivery cursors."""

import dataclasses
import os
import subprocess
import sys
import time
import typing as ty
from pathlib import Path

from ...claude import session_socket
from ...inbox import db
from ...watch import registry
from . import environment, process, state


def start(plan: dict[str, ty.Any], token: str) -> None:
    harness, channel = plan["harness"], plan["channel"]
    if registry.mine(channel, "wait"):
        return

    environment.validate(plan["settings"])
    path = db.get_db_path().parent / "restart-watchers.log"
    with path.open("a") as log:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lemonaid",
                "watch",
                "--self",
                "--channel",
                channel,
                *(
                    ["--codex-thread", plan["session_id"]]
                    if harness == "codex"
                    else ["--push", "--foreground"]
                ),
            ],
            env={
                **environment.apply(plan["settings"].get("environment", {})),
                "LEMONAID_RESTART_TOKEN": token,
                "LEMONAID_CHANNEL": channel,
                "LEMONAID_DB": str(db.get_db_path()),
            },
            cwd=plan["cwd"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )


def stamp(channel: str, session: session_socket.Session | None = None) -> None:
    token = os.environ.get("LEMONAID_RESTART_TOKEN", "")
    if not token:
        return

    with db.connect() as conn:
        operation = state.active(conn, channel)
        if operation and operation["token"] == token:
            root = process.inspect(os.getpid())
            state.evidence(
                conn,
                token,
                watcher=dataclasses.asdict(root) if root else {},
                scout_pid=session.pid if session else 0,
                scout_socket=session.socket if session else "",
            )


def ready(channel: str, token: str, harness: process.Identity) -> bool:
    with db.connect() as conn:
        operation = state.get(conn, token)
    saved = operation["evidence"].get("watcher")
    if not saved or not process.same(process.Identity(**saved)):
        return False

    evidence = operation["evidence"]
    if (
        channel.startswith("claude:")
        and evidence.get("scout_pid")
        and evidence["scout_pid"] != harness.pid
    ):
        return False

    if channel.startswith("claude:"):
        if evidence.get("scout_pid"):
            plan = operation["plan"]
            root = plan["settings"].get("native_homes", {}).get("claude") or plan["settings"].get(
                "environment", {}
            ).get("CLAUDE_CONFIG_DIR")
            if not root:
                return False
            entry = session_socket.find(plan["session_id"], Path(root))
            if (
                entry is None
                or entry.pid != harness.pid
                or entry.socket != evidence.get("scout_socket")
            ):
                return False
        elif harness not in process.ancestry(saved["pid"]):
            return False

    return any(w.pid == saved["pid"] for w in registry.mine(channel, "wait"))


def restore(plan: dict[str, ty.Any], timeout: float = 5) -> None:
    """An abort must leave a registered source watcher, or report lost delivery."""
    start(plan, "")
    deadline = time.monotonic() + timeout
    while not registry.mine(plan["channel"], "wait"):
        if time.monotonic() >= deadline:
            raise TimeoutError("Source watcher did not register; rearm delivery manually")
        time.sleep(0.1)


def check_source(harness: str, waiters: list[registry.Waiter]) -> None:
    if harness == "claude":
        delivery = [w for w in waiters if w.kind == "wait"]
        if not delivery or any("--push" not in w.command.split() for w in delivery):
            raise ValueError(
                "Claude restart requires a running push scout; background-waiter restoration "
                "is unsupported. Keep this harness running and use handoff instead."
            )
