"""Hand an inbox message to a Codex thread, leaving it pending until Codex accepts it."""

import contextlib
import datetime as dt
import os
import subprocess
import typing as ty
from collections import abc
from pathlib import Path

from .. import brief, daily_date, home
from ..config import load_config
from ..inbox import db
from ..inbox.channel import full_channel_id
from . import store


def own_thread(channel: str) -> str:
    """This process's Codex thread, when the watched channel is that thread's own."""
    thread = os.environ.get("CODEX_THREAD_ID", "")
    return thread if thread and channel == full_channel_id("codex", thread) else ""


def _with_status_note(inbox: Path, message: str) -> str:
    """*message*, and a reminder when the recipient's brief waits on Peter."""
    if brief.nudge.carries_note(message):
        return message

    with db.connect() as conn:
        path = brief.lemon.brief_of(conn, inbox.name)  # an inbox is named by its Lemon-ID
    reminder = brief.nudge.note(path.read_text()) if path and path.is_file() else ""
    return f"{message.rstrip()}\n\n{reminder}" if reminder else message


def _queue(thread: str, path: Path, message: str) -> None:
    try:
        result = subprocess.run(
            [
                "codex",
                "queue",
                "--thread",
                thread,
                "--message",
                f"lemonaid message: {message.rstrip()}",
            ],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise RuntimeError(f"Could not run codex queue: {error}") from error

    if result.returncode != 0:
        raise RuntimeError(
            f"codex queue exited {result.returncode}; {path.name} stays pending:\n"
            + (result.stderr or result.stdout).strip()
        )


def deliver_next(
    inbox: Path,
    thread: str,
    while_current: abc.Callable[[], ty.ContextManager[bool]] = lambda: contextlib.nullcontext(True),
) -> tuple[Path, str] | None:
    """Queue the oldest pending message into `thread`, then move it to done/.

    Raises `RuntimeError` with the file still pending if `codex queue` fails.
    Returns None while another receiver holds the inbox, so each message is
    handed out once. A process killed after Codex accepts the message but before the
    move delivers it again on the next watch. So does a recipient that stopped
    being current while the queue ran: the move happens inside `while_current`,
    only if it yields True, and otherwise the file stays pending and this returns None.
    The thread's first message of a day ends with `daily_date`'s line.
    """
    with home.guard.operation(), store.receive_lock(inbox, wait=False) as held:
        found = store.peek_next(inbox) if held else None
        if found is None:
            return None

        now, seen = dt.datetime.now(), daily_date.seen_path(full_channel_id("codex", thread))
        day_starts = load_config().inbox.day_starts
        date_line = daily_date.due(seen, now, day_starts)
        message = _with_status_note(inbox, found[1])
        _queue(thread, found[0], f"{message.rstrip()}\n\n{date_line}" if date_line else message)
        if date_line:
            daily_date.mark(seen, now, day_starts)
        with while_current() as current:
            return (store.mark_done(found[0]), found[1]) if current else None
