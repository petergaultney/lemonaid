"""Whether a process has exited since it was found, from a kqueue of its own.

kqueue follows the process rather than its pid, so it reports an exit that nobody has
reaped yet, and never mistakes a new process that took the pid for the old one;
`kill(pid, 0)` can tell neither from a live process.
"""

import select
from collections import abc


def watch(pid: int) -> abc.Callable[[], bool] | None:
    """Whether *pid* has exited since this call; None where there is no kqueue."""
    if not hasattr(select, "kqueue"):
        return None

    queue = select.kqueue()
    try:
        queue.control(
            [
                select.kevent(
                    pid,
                    select.KQ_FILTER_PROC,
                    select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                    select.KQ_NOTE_EXIT,
                )
            ],
            0,
        )
    except ProcessLookupError:  # exited already, reaped or not
        queue.close()
        return lambda: True

    def exited() -> bool:
        if not queue.closed and queue.control(None, 1, 0):
            queue.close()  # the event comes once
        return queue.closed

    return exited
