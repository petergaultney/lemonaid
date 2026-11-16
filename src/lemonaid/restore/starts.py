"""Starting lost lemons a few at a time, and keeping only the ones proven to run.

A typed line is not a lemon at work: a resume can start a fresh conversation
when the old one's transcript is gone, or exit straight to the shell. A lemon
counts as restored only when its own process runs in the window it was given;
one that fails is stopped and started once more, then reported.

Each lemon is checked again just before it starts, under the start lock that
`lemon resume` and `tell`'s autoresume also take: while restore works through
its list, a lead or a person may resume a lemon on it, or attach its brief to a
new one, and starting it again would run one conversation twice.
"""

import time
import typing as ty
from collections import abc

from ..audit import events
from ..inbox import db, ended
from ..messages import resume_log, start_lock, store
from . import report, run


class _Attempt(ty.NamedTuple):
    window: str  # the window this attempt made, "" if it made none
    why: str  # why it failed to start, "" when the line was typed
    seen: report.Seen | None = None  # its window, as it was closed for not running the lemon
    taken: str = ""  # why it was left alone, having come back without restore; "" if not


_ELSEWHERE = "brought back by someone else while restore ran"


def _taken(lemon: run.Lemon, terminal: run.Terminal, first: bool) -> str:
    """Why *lemon* came back, or was retired, since restore planned it; "" if it didn't.

    Only its process says so on a retry: restore's own first try may have re-registered
    its row and started its start log.
    """
    if first:
        with db.connect() as conn:
            row = db.get_by_channel(conn, lemon.channel, unread_only=False)
        if row is None or row.is_archived:
            return "its row was retired while restore ran"

        if not ended.revivable(row.metadata) or (
            lemon.lemon_id
            and resume_log.starting(
                resume_log.entries(store.mailbox_for_id(lemon.lemon_id)), time.time()
            )
        ):
            return _ELSEWHERE

    return _ELSEWHERE if terminal.found([lemon.row], False) else ""


def _start(lemon: run.Lemon, terminal: run.Terminal, first: bool) -> _Attempt:
    """Start *lemon* unless it came back without restore, holding its start lock from that
    check through typing its line. A resume that waited on the lock finds restore holding
    its own lock, and leaves the lemon to it (`revive`)."""
    with start_lock.held(lemon.channel):
        if taken := _taken(lemon, terminal, first):
            return _Attempt("", "", taken=taken)

        events.record(
            "restore-start", lemon.channel, "lost with its terminal", where=lemon.spot.where
        )
        window, why = terminal.open(lemon.spot, lemon.launch.cwd, lemon.launch.environment)
        if why or not window:
            return _Attempt("", why or "its window could not be made")

        return _Attempt(window, terminal.type(window, lemon.launch.line))


def _await(
    lemons: abc.Sequence[run.Lemon], terminal: run.Terminal, seconds: float, poll: float
) -> set[str]:
    deadline = time.monotonic() + seconds
    found: set[str] = set()
    while lemons:
        found |= terminal.running([lemon for lemon in lemons if lemon.channel not in found])
        if len(found) == len(lemons) or time.monotonic() >= deadline:
            break

        time.sleep(poll)
    return found


def _round(
    lemons: abc.Sequence[run.Lemon],
    terminal: run.Terminal,
    seconds: float,
    poll: float,
    first: bool,
) -> tuple[set[str], dict[str, _Attempt]]:
    """Start *lemons*: the channels proven running, and each one's attempt.

    A lemon not proven running has the window this attempt made closed, and only that
    one, so nothing runs under its name but the lemon itself.
    """
    attempts = {lemon.channel: _start(lemon, terminal, first) for lemon in lemons}
    running = _await(
        [
            each
            for each in lemons
            if not (attempts[each.channel].why or attempts[each.channel].taken)
        ],
        terminal,
        seconds,
        poll,
    )
    for lemon in lemons:
        attempt = attempts[lemon.channel]
        if lemon.channel not in running and attempt.window:
            attempts[lemon.channel] = attempt._replace(seen=terminal.seen(lemon.spot.where))
            terminal.close(attempt.window)
    return running, attempts


def _failed(
    lemon: run.Lemon, terminal: run.Terminal, why: str, seen: report.Seen | None
) -> report.Result:
    if not why:
        why = "its own conversation did not start in its window" + (
            f" ({report.detail(seen)})" if seen and report.detail(seen) else ""
        )

    return report.Result(
        lemon.channel,
        lemon.row.name or lemon.channel,
        lemon.spot.where,
        report.NOT_RESTORED,
        why,
    )


def start(
    lemons: abc.Sequence[run.Lemon],
    terminal: run.Terminal,
    parallel: int,
    seconds: float,
    progress: abc.Callable[[str], None],
    poll: float = 1.0,
) -> tuple[list[run.Lemon], list[report.Result]]:
    """(the lemons proven running in their windows, a result for each that is not).

    *parallel* lemons start at once, and each batch is proven before the next starts.
    A lemon that fails is started once more. One that came back without restore is
    left alone and reported as running.
    """
    started: list[run.Lemon] = []
    taken: list[report.Result] = []
    failed: list[report.Result] = []
    for at in range(0, len(lemons), parallel):
        batch = lemons[at : at + parallel]
        running, first = _round(batch, terminal, seconds, poll, first=True)
        again = [
            lemon
            for lemon in batch
            if lemon.channel not in running and not first[lemon.channel].taken
        ]
        retried, attempts = _round(again, terminal, seconds, poll, first=False)
        running |= retried
        attempts = first | attempts
        started += [lemon for lemon in batch if lemon.channel in running]
        taken += [
            report.Result(
                lemon.channel, lemon.row.name or lemon.channel, "", report.RUNNING, attempt.taken
            )
            for lemon in batch
            if (attempt := attempts[lemon.channel]).taken
        ]
        failed += [
            _failed(lemon, terminal, attempts[lemon.channel].why, attempts[lemon.channel].seen)
            for lemon in again
            if lemon.channel not in running and not attempts[lemon.channel].taken
        ]
        progress(
            f"{len(started) + len(taken)} of {len(lemons)} running, {len(failed)} not restored"
        )
    return started, [*taken, *failed]
