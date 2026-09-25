"""Deliver pending messages to Codex lemons by queueing them into their threads.

One service runs at a time, held by a lock beside the inboxes. `tell` starts it
when it writes to a Codex lemon, and it exits once no Codex inbox has anything
pending, so no lemon has to arm a waiter and nothing lingers.
"""

import contextlib
import fcntl
import sqlite3
import subprocess
import sys
import time
import typing as ty
from collections import abc
from pathlib import Path

from .. import brief
from ..inbox import db
from ..log import get_logger
from . import codex_delivery, store

_log = get_logger("messages.service")


def _lock_path() -> Path:
    root = store.inbox_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / ".delivery.lock"


def _try_lock() -> ty.IO | None:
    lock = open(_lock_path(), "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None

    return lock


def _inbox(path: Path) -> Path | None:
    try:
        lemon_id = brief.identity.from_path(path)
        return store.inbox_for_id(lemon_id) if lemon_id else None
    except (OSError, ValueError) as error:
        _log.warning("Skipping brief %s: %s", path, error)
        return None


def _claimed_recipients(conn: sqlite3.Connection) -> abc.Iterator[tuple[Path, str]]:
    for entry in brief.attached.everything(conn):
        found = entry.notification
        if not entry.channel.startswith("codex:") or found is None or found.is_archived:
            continue

        thread = found.metadata.get("session_id") or ""
        inbox = _inbox(entry.path)
        if thread and inbox is not None:
            yield inbox, thread


def codex_recipients(conn: sqlite3.Connection) -> abc.Iterator[tuple[Path, str]]:
    """(inbox, thread) for each live Codex lemon with an attached brief.

    An archived session is skipped: its messages stay pending in files until
    the lemon is seen again.
    """
    brief.attached.claim_pending(conn)
    yield from _claimed_recipients(conn)


def has_pending(conn: sqlite3.Connection, channel: str) -> bool:
    path = brief.attached.by_channel(conn, [channel]).get(channel)
    inbox = _inbox(path) if path is not None else None
    return inbox is not None and store.peek_next(inbox) is not None


def _current_thread(inbox: Path) -> str:
    with db.connect() as conn:
        return next((thread for found, thread in codex_recipients(conn) if found == inbox), "")


@contextlib.contextmanager
def _while_current(inbox: Path, thread: str) -> abc.Iterator[bool]:
    """Whether `thread` still receives `inbox`, with attachment and archive writes held off.

    The caller moves the message to done/ inside this, so a brief cannot move
    between the check and the move. Pending attachments are not claimed here:
    claiming commits, which would end the hold.
    """
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield next((t for found, t in _claimed_recipients(conn) if found == inbox), "") == thread
        finally:
            conn.rollback()


def _deliver_all(inbox: Path, thread: str) -> None:
    """Stops as soon as the brief moves to another session or this one is archived.

    A move while `codex queue` runs leaves that message pending too, so the new
    session gets it as well as the old one.
    """
    while _current_thread(inbox) == thread:
        delivered = codex_delivery.deliver_next(
            inbox, thread, lambda: _while_current(inbox, thread)
        )
        if delivered is None:
            return

        _log.info("delivered %s to codex thread %s", delivered[0].name, thread)


def _pass(retry_at: dict[Path, float], retry: float) -> bool:
    """Deliver what can be delivered now; whether anything is still pending."""
    with db.connect() as conn:
        recipients = list(codex_recipients(conn))

    pending = False
    for inbox, thread in recipients:
        if retry_at.get(inbox, 0.0) <= time.monotonic():
            try:
                _deliver_all(inbox, thread)
                retry_at.pop(inbox, None)
            except RuntimeError as error:
                _log.warning("delivery to %s failed; retrying in %.0fs: %s", inbox.name, retry, error)
                retry_at[inbox] = time.monotonic() + retry

        pending = pending or store.peek_next(inbox) is not None

    return pending


def serve(interval: float = 1.0, idle_exit: float = 120.0, retry: float = 30.0) -> bool:
    """Deliver until nothing is pending for `idle_exit` seconds (0: forever).

    Returns False at once if another service is running. Before exiting it
    releases the lock and looks again, so a message written just before a
    `tell` found the lock held is still delivered by someone.
    """
    lock = _try_lock()
    if lock is None:
        return False

    retry_at: dict[Path, float] = {}
    idle_since = time.monotonic()
    try:
        while True:
            if _pass(retry_at, retry):
                idle_since = time.monotonic()
            elif idle_exit and time.monotonic() - idle_since >= idle_exit:
                lock.close()
                if not _pass(retry_at, retry) or (lock := _try_lock()) is None:
                    return True

                idle_since = time.monotonic()

            time.sleep(interval)
    finally:
        lock.close()


def ensure_running() -> None:
    """Start a detached service unless one holds the lock."""
    lock = _try_lock()
    if lock is None:
        return

    lock.close()
    subprocess.Popen(
        [sys.executable, "-m", "lemonaid", "inbox", "deliver"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=Path.home(),
        start_new_session=True,
    )
    _log.info("started the message delivery service")
