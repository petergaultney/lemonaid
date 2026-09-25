"""Hand an inbox message to a Codex thread, leaving it pending until Codex accepts it."""

import contextlib
import os
import subprocess
import typing as ty
from collections import abc
from pathlib import Path

from ..inbox.channel import channel_id
from . import store

def own_thread(channel: str) -> str:
    """This process's Codex thread, when the watched channel is that thread's own."""
    thread = os.environ.get("CODEX_THREAD_ID", "")
    return thread if thread and channel == channel_id("codex", thread) else ""


def _queue(thread: str, path: Path, message: str) -> None:
    try:
        result = subprocess.run(
            ["codex", "queue", "--thread", thread, "--message", f"lemonaid message: {message.rstrip()}"],
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
    """
    with store.receive_lock(inbox, wait=False) as held:
        found = store.peek_next(inbox) if held else None
        if found is None:
            return None

        _queue(thread, *found)
        with while_current() as current:
            return (store.mark_done(found[0]), found[1]) if current else None
