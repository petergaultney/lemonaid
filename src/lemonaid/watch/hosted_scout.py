"""One lemon's push scout, run as a thread of the scout host until its session or brief ends."""

import contextlib
import functools
import typing as ty
from collections import abc
from pathlib import Path

from ..brief import attached, identity
from ..claude import session_socket
from ..hooks import session_gate
from ..inbox import db
from ..launch.restart import gates
from ..log import get_logger
from ..messages import store, waiter
from . import (
    attachment,
    batch_wait,
    codex_scout,
    cursors,
    delivery,
    notes,
    own_edits,
    pr_poller,
    push_scout,
    scout_roster,
    wait_state,
    waiter_lock,
    waits,
)

_log = get_logger("watch.hosted_scout")

Outcome = ty.Literal["ended", "retry", "stopped"]  # ended: its registration is done with


def _brief(channel: str, lemon_id: str) -> Path | None:
    with db.connect() as conn:
        path = attached.by_channel(conn, [channel]).get(channel)
    if path is None or identity.from_path(path) != lemon_id:
        return None

    return path


class _Harness(ty.NamedTuple):
    output: delivery.Deliver
    alive: abc.Callable[[], bool]
    writer: str
    session: session_socket.Session | None
    sources: tuple[tuple[Path, ...], tuple[int, ...]] = ((), ())  # whose changes wake the scout


def _harness(registration: scout_roster.Registration) -> _Harness | str:
    """How to deliver to the lemon's harness, or why it can't be."""
    if thread := registration.thread:
        if problem := delivery.codex_setup_problem():
            return problem

        return _Harness(
            codex_scout.to_thread(thread), codex_scout.liveness(thread), f"codex-{thread}", None
        )

    session = push_scout.session(registration.channel.removeprefix("claude:"), wait=30)
    if problem := push_scout.problem(session):
        return problem

    assert session is not None  # problem() names a missing session
    return _Harness(
        push_scout.to_session(session),
        functools.partial(session_socket.alive, session),
        own_edits.claude_writer(session.session_id),
        session,
        ((session_socket.claude_dir() / "sessions" / f"{session.pid}.json",), (session.pid,)),
    )


def run(
    registration: scout_roster.Registration,
    stopping: abc.Callable[[], bool],
    pacing: waits.Waits = waits.TIMERS,
) -> Outcome:
    """Deliver batches until the lemon is gone (ended) or *stopping* says so (stopped).

    `retry` means it could not run now: another waiter holds the lemon's lock, or
    delivery failed. Undelivered changes stay pending for the next attempt.
    """
    lemon_id, channel = registration.lemon_id, registration.channel
    told_to_stop = stopping

    def stopping() -> bool:
        """Also checked on the wake its registration's removal or replacement causes."""
        return told_to_stop() or scout_roster.read(lemon_id) != registration

    try:
        path = _brief(channel, lemon_id)
    except (OSError, ValueError) as error:
        _log.warning("no scout for %s: %s", lemon_id, error)
        return "retry"

    if path is None:
        _log.info(
            "no scout for %s: no brief with that Lemon-ID is attached to %s", lemon_id, channel
        )
        return "ended"

    harness = _harness(registration)
    if isinstance(harness, str):
        _log.info("no scout for %s: %s", lemon_id, harness)
        return "retry" if registration.thread else "ended"

    def still() -> bool:
        return not stopping() and harness.alive() and attachment.holds(path, channel, harness.alive)

    wait_state.lock_path(lemon_id).parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(wait_state.lock_path(lemon_id), grace=5)  # an old scout exits
    if lock is None:
        return "retry"

    inbox = store.inbox_for_id(lemon_id)
    session_gate.mark(own_edits.root(), harness.writer, path)
    try:
        wait_state.clear_delivery(lemon_id)
        with (
            waiter.armed(inbox),
            push_scout.logged(lemon_id, harness.session, stopping)
            if harness.session
            else contextlib.nullcontext(),
        ):
            if harness.session:
                push_scout.announce(harness.session)
            pr_poller.ensure_running()
            while still():
                batch_wait.wait(
                    path,
                    inbox,
                    cursors.root() / lemon_id,
                    harness.writer,
                    gates.deliver(channel, harness.output),
                    still,
                    cwd=Path(registration.cwd),
                    notes=notes.reader(
                        notes.default_dir(), "codex" if registration.thread else "claude"
                    ),
                    restart_requested=stopping,
                    beat=functools.partial(wait_state.beat, lemon_id),
                    pacing=pacing,
                    harness=(
                        (*harness.sources[0], scout_roster.path(lemon_id)),
                        harness.sources[1],
                    ),
                )
    except waiter.AlreadyArmed as error:
        _log.info("scout for %s waits: %s", lemon_id, error)
        return "retry"
    except (delivery.Failed, ValueError, OSError) as error:
        _log.warning("scout for %s failed: %s; undelivered changes stay pending", lemon_id, error)
        return "retry"
    finally:
        wait_state.clear_delivery(lemon_id)
        lock.close()
    return "stopped" if stopping() else "ended"
