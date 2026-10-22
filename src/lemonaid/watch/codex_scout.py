"""A Codex lemon's scout: `lemonaid watch --self --codex-thread --push`, detached, while its thread runs.

It queues each batch into the thread with `codex queue` instead of exiting with it, so the
lemon never rearms a watcher. `codex_waiter` starts it; it holds the same lock as any
unified watcher.
"""

import time
from collections import abc
from pathlib import Path

from ..brief import identity
from ..codex import channels, processes
from ..inbox import db
from ..log import LOG_PATH
from . import codex_waiter, delivery, push_scout

_INSTRUCTION = (
    "Read the changed sources and handle the entire batch. lemonaid is watching for you "
    "and queues the next batch into this thread"
)
_ALIVE_EVERY = 30.0


def thread_alive(thread: str) -> bool:
    """False only when no Codex process, the shared daemon included, has *thread*'s rollout open."""
    open_threads = processes.open_threads()
    return open_threads is None or thread in open_threads


def liveness(thread: str) -> abc.Callable[[], bool]:
    """A cheap `thread_alive` for a loop: the first check comes `_ALIVE_EVERY` seconds in,
    leaving a starting session time to open its rollout."""
    checked, alive = time.monotonic(), True

    def still() -> bool:
        nonlocal checked, alive
        if time.monotonic() - checked >= _ALIVE_EVERY:
            checked, alive = time.monotonic(), thread_alive(thread)
        return alive

    return still


def to_thread(thread: str) -> delivery.Deliver:
    queue = delivery.to_codex(thread, "lemonaid watch", _INSTRUCTION)

    def deliver(message: str) -> None:
        if not thread_alive(thread):
            raise delivery.Failed(f"no live Codex process owns thread {thread}")

        queue(message)

    return deliver


def status_line(thread: str) -> str:
    return (
        f"thread {thread}: batches are queued into it with `codex queue`"
        if thread_alive(thread)
        else f"thread {thread}: no Codex process has it open; batches wait for its next session"
    )


def ensure_for(thread: str, path: Path) -> bool:
    """Whether a scout pushes into *thread* for the lemon whose brief is *path*, starting one if none runs."""
    try:
        lemon_id = identity.read(path.read_text())
    except (OSError, ValueError):
        return False

    with db.connect() as conn:
        channel = channels.for_session(conn, thread)
    return (
        bool(lemon_id)
        and codex_waiter.ensure(channel, thread, lemon_id)
        and push_scout.running(lemon_id)
    )


def start(channel: str, thread: str, lemon_id: str) -> int:
    if codex_waiter.ensure(channel, thread, lemon_id):
        print("push scout running" if push_scout.running(lemon_id) else "watcher running")
        return 0

    print(f"not started: the scout did not take its lock; see {LOG_PATH}")
    return 2
