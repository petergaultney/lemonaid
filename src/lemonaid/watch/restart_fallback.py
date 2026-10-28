"""Replacing the watchers that did not restart when asked, by stopping them and starting again."""

import time
from collections import abc

from ..codex import channels
from ..inbox import db
from ..log import get_logger
from . import codex_waiter, push_scout, registry, stopping

_log = get_logger("watch.restart_fallback")

_BY = "lemonaid watch restart"


def _unrestarted(asked: abc.Iterable[registry.Waiter]) -> list[registry.Waiter]:
    """Those of *asked* still running under the registration they had when asked."""
    was = {(w.pid, w.started) for w in asked}
    return [w for w in registry.running() if (w.pid, w.started) in was]


def stuck(asked: list[registry.Waiter], wait: float) -> list[registry.Waiter]:
    deadline = time.monotonic() + wait
    remaining = _unrestarted(asked)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.5)
        remaining = _unrestarted(remaining)
    return remaining


def _start_scout(waiter: registry.Waiter) -> bool | None:
    """Start a scout in place of *waiter*; None when it was not a push scout."""
    if push_scout.FLAG not in waiter.command.split():
        return None

    lemon_id = waiter.targets[0]
    if waiter.channel.startswith("claude:"):
        return push_scout.ensure(waiter.channel.removeprefix("claude:"), lemon_id)

    if waiter.channel.startswith("codex:"):
        with db.connect() as conn:
            row = db.get_by_channel(conn, waiter.channel, unread_only=False)
        thread = channels.owner_id(waiter.channel, row.metadata if row else {}, {})
        return codex_waiter.ensure(waiter.channel, thread, lemon_id)

    return None


def replace(waiters: abc.Iterable[registry.Waiter]) -> abc.Iterator[str]:
    """Stop each of *waiters* and start its push scout again; a line for each.

    Any other waiter stays stopped, and its lemon rearms it on seeing why it ended.
    """
    for waiter in waiters:
        name = ", ".join(waiter.targets)
        try:
            stopping.stop(waiter, _BY)
        except TimeoutError as error:
            _log.warning("%s", error)
            yield f"{name}: pid {waiter.pid} did not exit; stop it with `kill {waiter.pid}`"
            continue

        started = _start_scout(waiter)
        if started is None:
            yield f"{name}: stopped pid {waiter.pid}; its lemon must rearm `{waiter.command}`"
        elif started:
            yield f"{name}: replaced scout pid {waiter.pid}"
        else:
            yield f"{name}: stopped scout pid {waiter.pid} but could not start another; see `lemonaid watch reconcile`"
