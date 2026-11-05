"""One detached stop, start elsewhere, and tidy-up; native resume owns the conversation.

A move shares restart's operation record and channel barrier, so delivery and
autoresume hold off while the lemon is between its old terminal and its new one.
"""

import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path

from ...claude import trust
from ...config import load_config
from ...front_end import pick
from ...inbox import db
from ...watch import registry, stopping
from ..restart import native, process, state
from . import planning
from .destination import Destination

_REGISTER_SECONDS = 30  # a new window starts a shell before the harness


class _Stopped(ValueError):
    """The lemon was stopped and nothing was started for it."""


def _checked(plan: dict) -> None:
    with db.connect() as conn:
        current = planning.build(
            conn, plan["channel"], Destination(**plan["destination"]), load_config(), plan["force"]
        )
        if any(current[k] != plan[k] for k in ("source", "line", "lemon_id", "patch")):
            raise ValueError("The process, attachment or resume command changed after preflight")

        if conn.execute(
            "SELECT 1 FROM brief_handoffs WHERE source = ? AND phase NOT IN ('complete','failed')",
            (plan["channel"],),
        ).fetchone():
            raise ValueError("A handoff is in progress")


def _record(channel: str, patch: dict) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = json_patch(metadata, ?) WHERE channel = ?",
            (json.dumps(patch), channel),
        )
        conn.commit()


def _moved_row(plan: dict) -> db.Notification:
    _record(plan["channel"], plan["patch"])
    with db.connect() as conn:
        row = db.get_by_channel(conn, plan["channel"], unread_only=False)
    if row is None:
        raise ValueError("The lemon's inbox row disappeared during the move")

    return row


def _execute(token: str, plan: dict) -> None:
    _checked(plan)
    config = load_config()
    destination = Destination(**plan["destination"])
    front_end = pick.named(destination.front_end)
    if front_end is None or front_end.start is None:
        raise ValueError(f"lemonaid can't start a lemon in {destination.front_end}")

    if plan["claude_trust"]:
        trust.grant(Path(destination.directory), trust.config_file())
    moving = front_end.relocation
    socket, old_tty = plan["from"]["instance"], plan["from"]["tty"]
    if moving:
        moving.prepare(socket, old_tty, destination.workspace, destination.directory, config)
    state.update(token, "stopping")
    process.terminate(process.Identity(**plan["source"]))
    for waiter in registry.mine(plan["channel"]):
        stopping.stop(waiter, f"move {token}")
    state.update(token, "starting")
    try:
        # The row says where the lemon is now, so a failed start resumes it there.
        row = _moved_row(plan)
    except (ValueError, OSError) as error:
        raise _Stopped(str(error)) from error

    if why := front_end.start(row, config, plan["prompt"]):
        raise _Stopped(why)

    state.update(token, "registering")

    deadline = time.monotonic() + _REGISTER_SECONDS
    while (started := native.replacement(plan["channel"], plan["source"])) is None:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "The resumed process did not register; look in the destination for a startup dialog"
            )
        time.sleep(0.2)
    tty = "/dev/" + started.tty
    _record(plan["channel"], moving.location(socket, tty) if moving else {"tty": tty})
    left = (
        moving.leave(socket, old_tty, destination.workspace, config)
        if moving
        else f"its old {destination.front_end} tab stays open at its shell"
    )
    state.update(token, "started", left_behind=left)


def run(token: str) -> None:
    operation = state.get(token)
    with state._path(token + ".lock").open("a+") as lock:
        with state.barrier(operation["plan"]["channel"], exclusive=True):
            operation = state.get(token)
            if operation["phase"] != "planned":
                return  # Never repeat an uncertain stop or start.
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
        plan = operation["plan"]
        try:
            _execute(token, plan)
        except _Stopped as error:
            state.update(
                token,
                "failed",
                error=f"{error}. The lemon is stopped; `lemonaid lemon resume "
                f"{plan['lemon_id']}` starts it in {plan['cwd']}",
            )
        except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
            source_alive = process.same(process.Identity(**plan["source"]))
            state.update(token, "failed" if source_alive else "partial", error=str(error))


def spawn(token: str) -> None:
    with state._path(token + ".log").open("a") as log:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid.launch.move.worker", token],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
