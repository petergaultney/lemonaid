"""Run a hosted scout in a thread of the test process, which holds the host's lock.

Delivery goes only to the test's own sockets and patched queues: `conftest` moves the
database, state and Claude directory into the test's directory.
"""

import contextlib
import threading
import typing as ty
from collections import abc

from lemonaid.watch import hosted_scout, scout_roster, waiter_lock


@contextlib.contextmanager
def hosting() -> abc.Iterator[None]:
    path = scout_roster.host_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(path, grace=0)
    assert lock is not None
    try:
        yield
    finally:
        lock.close()


class Running(ty.NamedTuple):
    thread: threading.Thread
    stop: threading.Event
    outcome: list[hosted_scout.Outcome]

    def join(self, timeout: float = 10) -> hosted_scout.Outcome:
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "the scout did not end"
        return self.outcome[0]


def start(lemon_id: str, channel: str, thread: str = "") -> Running:
    registration = scout_roster.register(lemon_id, channel, thread, "")
    stop = threading.Event()
    outcome: list[hosted_scout.Outcome] = []
    runner = threading.Thread(
        target=lambda: outcome.append(hosted_scout.run(registration, stop.is_set)), daemon=True
    )
    runner.start()
    return Running(runner, stop, outcome)


def run(lemon_id: str, channel: str, thread: str = "") -> hosted_scout.Outcome:
    return start(lemon_id, channel, thread).join()
