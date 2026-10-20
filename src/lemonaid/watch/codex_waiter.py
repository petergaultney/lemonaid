"""Start a Codex lemon's push scout, and restore it for a live, idle lemon that has none."""

import os
import sqlite3
import subprocess
import sys
import time
import typing as ty
from pathlib import Path

from ..brief import attached, identity, status
from ..brief.handoff import state as handoff_state
from ..codex import channels, processes, utils
from ..inbox import db
from ..log import LOG_PATH, get_logger
from . import deaf_waiter, wait_state, waiter_lock

_log = get_logger("watch.codex_waiter")

RETRY_SECONDS = 60.0  # between restores of one lemon, so a scout that keeps failing is not restarted every refresh
_restored: dict[str, float] = {}


def _spawn(channel: str, thread: str) -> None:
    with LOG_PATH.open("a") as log:
        subprocess.Popen(
            [
                *(sys.executable, "-m", "lemonaid", "watch", "--self", "--push", "--foreground"),
                *("--codex-thread", thread),
            ],
            env={
                **os.environ,
                "CODEX_THREAD_ID": thread,
                "LEMONAID_CHANNEL": channel,
                "LEMONAID_DB": str(db.get_db_path()),
            },
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            cwd=Path.home(),
            start_new_session=True,
        )


def ensure(channel: str, thread: str, lemon_id: str) -> bool:
    deaf_waiter.clear(lemon_id, channel)
    if wait_state.is_armed(lemon_id):
        return True
    path = wait_state.lock_path(lemon_id).with_suffix(".start.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(path, grace=0)
    if lock is None:
        return False
    try:
        if not wait_state.is_armed(lemon_id):
            _spawn(channel, thread)
            _log.info("starting Codex push scout channel=%s thread=%s", channel, thread)
        armed = wait_state.is_armed(lemon_id, grace=3)
        if not armed:
            _log.warning(
                "restored watcher for %s did not remain armed; refresh will retry", channel
            )
        return armed
    except OSError as error:
        _log.warning("could not restore watcher for %s: %s", channel, error)
        return False
    finally:
        lock.close()


def _due(lemon_id: str) -> bool:
    """Whether to try restoring *lemon_id* now, counting this as the attempt."""
    now = time.monotonic()
    if now - _restored.get(lemon_id, float("-inf")) < RETRY_SECONDS:
        return False

    _restored[lemon_id] = now
    return True


class Restored(ty.NamedTuple):
    started: list[str]  # Lemon-IDs
    unsettled: bool  # a lemon's liveness was unknown, or its scout did not start


def restore(conn: sqlite3.Connection, owners: dict[str, set[str]] | None = None) -> Restored:
    """A scout for every live, idle Codex lemon whose brief isn't done and that has no watcher."""
    from ..messages import recipient, store, waiter

    if owners is None:
        owners = processes.thread_ttys()
    if owners is None:
        return Restored([], True)

    started, unsettled = [], False
    for entry in attached.everything(conn):
        row = entry.notification
        if not entry.channel.startswith("codex:") or row is None or row.is_archived:
            continue
        thread = channels.owner_id(entry.channel, row.metadata, {})
        if (
            not thread
            or row.turn_at is not None
            or owners.get(thread) != {row.metadata.get("tty")}
            or utils.find_session_path(thread) is None
            or channels.for_session(conn, thread) != entry.channel
        ):
            continue
        try:
            text = entry.path.read_text()
            lemon_id = identity.read(text)
        except (OSError, ValueError):
            continue
        if (
            status.split(text).status == "done"
            or wait_state.is_armed(lemon_id)
            or waiter.is_armed(store.inbox_for_id(lemon_id))
            or handoff_state.pending_source(conn, entry.path, entry.channel, time.time())
        ):
            continue

        alive = recipient.harness_alive(row)
        if alive is None:
            unsettled = True
        elif alive and _due(lemon_id):
            if ensure(entry.channel, thread, lemon_id):
                started.append(lemon_id)
            else:
                unsettled = True
    return Restored(started, unsettled)
