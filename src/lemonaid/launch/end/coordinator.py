"""Ending a lemon, inside the reservation restart uses to keep delivery, autoresume and
the inbox watcher away while its harness stops.

The inbox card is archived before the reservation ends, so the watcher never sees a
harness gone from a live pane, which it would take for a crash for restore to bring back.
"""

import sqlite3
import subprocess
import time
from pathlib import Path

from ...audit import events
from ...brief import archive
from ...config import load_config
from ...inbox import db, ended
from ...watch import lemon_restart, registry, stopping
from ..restart import pane, process, state
from . import closing, plan

_COMMAND = "lemonaid lemon end"


def _card(channel: str, by: str) -> list[str]:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if row is None or row.is_archived:
            return []

        db.archive(conn, row.id, f"lemon end by {by}", cause=ended.ENDED, by=by)
    events.record("inbox-archive", channel, "lemon end")
    return ["archived its inbox card"]


def _waiters(one: lemon_restart.Lemon, by: str) -> list[str]:
    lines = []
    for waiter in lemon_restart.every(one, registry.running()):
        what = f"{waiter.kind} waiter ({', '.join(waiter.targets)}), pid {waiter.pid}"
        try:
            stopping.stop(waiter, f"lemon end by {by}", command=_COMMAND)
        except TimeoutError:
            lines.append(f"its {what} did not exit; stop it with `kill {waiter.pid}`")
            continue

        lines.append(f"stopped its {what}")
    return lines


def _brief(path: Path, channel: str) -> str:
    if archive.is_archived(path):
        return "its brief was already in the attic"

    try:
        with db.connect() as conn:
            moved = archive.archive(
                conn, path, time.time(), {channel} if channel else frozenset(), why="lemon end"
            )
    except (OSError, ValueError, sqlite3.Error) as error:
        return f"kept its brief {path.name}: {error}"

    return f"archived its brief to {moved}"


def _finish(planned: dict) -> list[str]:
    one = lemon_restart.Lemon(planned["lemon_id"], planned["channel"], Path(planned["brief"]))
    return [
        *_card(planned["channel"], planned["by"]),
        *_waiters(one, planned["by"]),
        _brief(one.brief, one.channel),
    ]


def _stop(token: str, planned: dict) -> list[str]:
    with db.connect() as conn:
        current = plan.build(
            conn, planned["channel"], load_config(), planned["expected"], planned["by"]
        )
    if any(current[k] != planned[k] for k in ("lemon_id", "source", "pane")):
        raise ValueError("Its process or pane changed after the check; nothing was stopped")

    target = pane.Pane(**planned["pane"])
    source = process.Identity(**planned["source"])
    exit_option = pane.exit_option(target)
    pane.preserve(target)
    state.update(token, "stopping")
    try:
        process.terminate(source)
    except (ValueError, TimeoutError):
        pane.restore(target, exit_option)
        raise

    return [
        f"stopped its harness, pid {source.pid}",
        *_finish(planned),
        closing.close(target, exit_option, load_config().places.protected_sessions),
    ]


def run(planned: dict) -> list[str]:
    """End the lemon *planned* (from `plan.build`) describes; a line for each thing done or left."""
    if planned["source"] is None:
        lines = _finish(planned)
    else:
        token = state.reserve(planned)
        try:
            lines = _stop(token, planned)
        except (ValueError, OSError, TimeoutError, subprocess.SubprocessError) as error:
            stopped = not process.same(process.Identity(**planned["source"]))
            state.update(token, "partial" if stopped else "failed", error=str(error))
            raise

        state.update(token, "ended", done=lines)
    events.record("lemon-end", planned["lemon_id"], f"by {planned['by']}")
    return lines
