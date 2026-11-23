"""A Codex lemon's scout: `lemonaid watch --self --codex-thread --push`, in the scout host, while its thread runs.

It queues each batch into the thread with `codex queue` instead of exiting with it, so the
lemon never rearms a watcher. `codex_waiter` registers it; it holds the same lock as any
unified watcher.
"""

import subprocess
import time
from collections import abc
from pathlib import Path

from ..brief import identity
from ..codex import channels, processes
from ..launch.restart import process
from ..log import LOG_PATH, get_logger
from . import batch_text, codex_waiter, delivery, process_exit, push_scout

_log = get_logger("watch.codex_scout")
_NEXT = "queues the next batch into this thread"
_ALIVE_EVERY = 30.0


def thread_alive(thread: str) -> bool:
    """False only when no Codex process, the shared daemon included, runs *thread*."""
    open_threads = processes.open_threads(delivery.LISTED_WITHIN)
    return open_threads is None or thread in open_threads


def _follow(thread: str) -> tuple[processes.Running | None, abc.Callable[[], bool] | None]:
    """The process running *thread*, and whether it has exited since.

    The listing may be two seconds old, so once its pid is watched, a process that took the
    pid since counts as the owner having exited.
    """
    owner = processes.owner(thread, delivery.LISTED_WITHIN)
    exited = process_exit.watch(owner.pid) if owner else None
    if owner is None or exited is None or exited():
        return owner, exited

    try:
        found = process.inspect(owner.pid)
    except (OSError, subprocess.SubprocessError) as error:
        _log.warning("could not confirm Codex process %d: %s", owner.pid, error)
        return owner, None  # listed every `_ALIVE_EVERY` seconds instead

    return owner, exited if found and found.started == owner.started else lambda: True


def liveness(thread: str) -> tuple[abc.Callable[[], bool], tuple[int, ...]]:
    """A cheap `thread_alive` for a loop, and the pid whose exit should wake the loop.

    Without kqueue it lists processes every `_ALIVE_EVERY` seconds, as it does once its
    process is gone. The first check comes that long after the start, leaving a starting
    session time to report itself.
    """
    owner, exited = _follow(thread)
    checked, alive = time.monotonic(), True

    def still() -> bool:
        nonlocal owner, exited, checked, alive
        if exited is not None and exited():
            exited, checked = None, float("-inf")
        if time.monotonic() - checked >= _ALIVE_EVERY:
            checked = time.monotonic()
            if owner is None or exited is None or processes.switched(owner):
                owner, exited = _follow(thread)
                alive = owner is not None or thread_alive(thread)
        return alive

    return still, (owner.pid,) if owner else ()


def to_thread(thread: str) -> delivery.Deliver:
    queue = delivery.queue_text(thread, "lemonaid watch", lambda m: batch_text.compose(m, _NEXT))

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

    channel = channels.channel(thread)
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
