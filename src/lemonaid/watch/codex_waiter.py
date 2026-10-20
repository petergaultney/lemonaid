"""Restore subscribed Codex waiters after a missed hook or a failed rearm."""

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from ..brief import attached, handoff_state, identity
from ..codex import channels, processes, utils
from ..inbox import db
from ..log import LOG_PATH, get_logger
from . import wait_requirements, wait_state, waiter_lock

_log = get_logger("watch.codex_waiter")


def _spawn(channel: str, thread: str) -> None:
    with LOG_PATH.open("a") as log:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid", "watch", "--self", "--codex-thread", thread],
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
            _log.info("restoring subscribed Codex watcher channel=%s thread=%s", channel, thread)
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


def restore(conn: sqlite3.Connection, owners: dict[str, set[str]] | None = None) -> None:
    """Called on inbox startup/refresh; require a live harness and verified alias owner."""
    from ..messages import recipient, store, waiter

    if owners is None:
        owners = processes.thread_ttys()
    if owners is None:
        return
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
            wait_requirements.needs_unified(text, False)
            and not wait_state.is_armed(lemon_id)
            and not waiter.is_armed(store.inbox_for_id(lemon_id))
            and not handoff_state.pending_source(conn, entry.path, entry.channel, time.time())
            and recipient.harness_alive(row) is True
        ):
            ensure(entry.channel, thread, lemon_id)
