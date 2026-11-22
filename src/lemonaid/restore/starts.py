"""Starting lost lemons a few at a time, and handing on each one as soon as it runs.

A typed line is not a lemon at work: a resume can start a fresh conversation
when the old one's transcript is gone, or exit straight to the shell. A lemon
counts as restored only when its own process runs in the window it was given;
one that fails is stopped and started once more, then reported.

Up to `parallel` lemons are starting at any moment, and the next one starts as soon as
one of them runs or is given up on, so a slow lemon holds up no other. A lemon a person
asked for starts next; the rest start most recently heard from first.

Each lemon is checked again just before it starts: its row and start log under the start
lock that `lemon resume` and `tell`'s autoresume also take, and its process once for each
round of starts, since asking every process costs most of a second. While restore works
through its list, a lead or a person may resume a lemon on it, or attach its brief to a
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
    taken: str = ""  # why it was left alone, having come back without restore; "" if not


class _Starting(ty.NamedTuple):
    lemon: run.Lemon
    attempt: _Attempt
    since: float  # when its line was typed, by the monotonic clock
    first: bool


_ELSEWHERE = "brought back by someone else while restore ran"


def _taken(lemon: run.Lemon, first: bool, running: bool) -> str:
    """Why *lemon* came back, or was retired, since restore planned it; "" if it didn't.
    *running* is whether its process ran anywhere as this round of starts began.

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

    return _ELSEWHERE if running else ""


def _start(lemon: run.Lemon, terminal: run.Terminal, first: bool, running: bool) -> _Attempt:
    """Start *lemon* unless it came back without restore, holding its start lock from that
    check through typing its line. A resume that waited on the lock finds restore holding
    its own lock, and leaves the lemon to it (`revive`)."""
    with start_lock.held(lemon.channel):
        if taken := _taken(lemon, first, running):
            return _Attempt("", "", taken=taken)

        events.record(
            "restore-start", lemon.channel, "lost with its terminal", where=lemon.spot.where
        )
        window, why = terminal.open(lemon.spot, lemon.launch.cwd, lemon.launch.environment)
        if why or not window:
            return _Attempt("", why or "its window could not be made")

        return _Attempt(window, terminal.type(window, lemon.launch.line))


def _heard(lemon: run.Lemon) -> float:
    return max(lemon.row.created_at, lemon.row.turn_at or 0.0)


def _pick(waiting: list[tuple[run.Lemon, bool]], asked: abc.Set[str]) -> tuple[run.Lemon, bool]:
    """Take the next lemon to start out of *waiting*: one a person asked for, else the one
    heard from most recently."""
    at = max(
        range(len(waiting)),
        key=lambda i: (waiting[i][0].channel in asked, _heard(waiting[i][0])),
    )
    return waiting.pop(at)


def _failed(lemon: run.Lemon, why: str, seen: report.Seen | None) -> report.Result:
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


def _gave_up(each: _Starting, terminal: run.Terminal) -> report.Result:
    """Close the window this attempt made, and only that one, so nothing runs under the
    lemon's name but the lemon itself, and mark it lost again with why.

    The attempt may have registered the lemon before it stopped, and the inbox's watcher
    would archive a registered row whose pane is gone.
    """
    seen = terminal.seen(each.lemon.spot.where) if each.attempt.window else None
    if each.attempt.window:
        terminal.close(each.attempt.window)
    failed = _failed(each.lemon, each.attempt.why, seen)
    with db.connect() as conn:
        db.restore_failed(conn, failed.channel, failed.detail)
    return failed


def start(
    lemons: abc.Sequence[run.Lemon],
    terminal: run.Terminal,
    parallel: int,
    seconds: float,
    progress: abc.Callable[[str], None],
    asked: abc.Callable[[], abc.Set[str]] = frozenset,
    poll: float = 1.0,
) -> abc.Iterator[run.Lemon | report.Result]:
    """Each lemon as soon as it is proven running in its window, or a result for one that
    is not: left alone, having come back without restore, or not restored.

    *asked* gives the channels a person asked for, read before each start. A lemon that
    doesn't run within *seconds* of its line is started once more. A lemon not handed on
    as running gives up the window reserved for it.
    """
    waiting = [(lemon, True) for lemon in lemons]
    starting: dict[str, _Starting] = {}
    back = failed = 0
    while waiting or starting:
        changed = False
        picked = [
            _pick(waiting, asked()) for _ in range(min(len(waiting), parallel - len(starting)))
        ]
        elsewhere = terminal.found([lemon.row for lemon, _ in picked], False) if picked else set()
        for lemon, first in picked:
            attempt = _start(lemon, terminal, first, lemon.channel in elsewhere)
            if attempt.taken:
                terminal.release(lemon.spot)
                back, changed = back + 1, True
                yield report.Result(
                    lemon.channel,
                    lemon.row.name or lemon.channel,
                    "",
                    report.RUNNING,
                    attempt.taken,
                )
            else:
                starting[lemon.channel] = _Starting(lemon, attempt, time.monotonic(), first)

        typed = [each.lemon for each in starting.values() if not each.attempt.why]
        running = terminal.running(typed) if typed else set()
        now = time.monotonic()
        for each in list(starting.values()):
            if each.lemon.channel in running:
                del starting[each.lemon.channel]
                back, changed = back + 1, True
                yield each.lemon
            elif each.attempt.why or now - each.since >= seconds:
                del starting[each.lemon.channel]
                result = _gave_up(each, terminal)
                if each.first:
                    waiting.append((each.lemon, False))
                    continue

                terminal.release(each.lemon.spot)
                failed, changed = failed + 1, True
                yield result

        if changed:
            progress(f"{back} of {len(lemons)} running, {failed} not restored")
        elif starting:
            time.sleep(poll)
