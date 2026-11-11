"""Starting lost lemons a few at a time, and keeping only the ones proven to run.

A typed line is not a lemon at work: a resume can start a fresh conversation
when the old one's transcript is gone, or exit straight to the shell. A lemon
counts as restored only when its own process runs in the window it was given;
one that fails is stopped and started once more, then reported.
"""

import time
import typing as ty
from collections import abc

from ..inbox import db
from . import launch, report


class Spot(ty.NamedTuple):
    where: str  # as a person names it
    was: str  # where its row recorded it, when that was taken; "" when it goes back there
    at: ty.Any  # the front end's own record of the spot, read only by that front end


class Relinked(ty.NamedTuple):
    lines: list[str]  # each row pointed at the pane its lemon runs in, as a person reads it
    json: list[dict]


class Lemon(ty.NamedTuple):
    row: db.Notification
    spot: Spot
    launch: launch.Launch
    lemon_id: str  # its brief's Lemon-ID, "" without a brief
    rearm: str  # the prompt that rearms its brief's waiters, "" when there are none
    note: str  # what to tell it about processes that died with the terminal, "" if none

    @property
    def channel(self) -> str:
        return self.row.channel


class Terminal(ty.NamedTuple):
    """What restore asks of the front end it brings lemons back into."""

    place: abc.Callable[
        [abc.Iterable[db.Notification]],
        tuple[list[tuple[db.Notification, Spot]], list[tuple[db.Notification, str]]],
    ]
    """(each lost row it can place, with its spot, in the order to start them; each row it
    can't, with why)."""
    open: abc.Callable[[Spot, str, abc.Mapping[str, str]], tuple[str, str]]
    """Open a spot's window: (the window it made or reused, why not or "")."""
    type: abc.Callable[[str, str], str]  # type a line into the window made; why not, or ""
    close: abc.Callable[[str], None]  # close a window restore made, and only such a window
    running: abc.Callable[[abc.Sequence[Lemon]], set[str]]
    """The channels among these whose own process runs in its spot; their rows are
    pointed there."""
    seen: abc.Callable[[str], report.Seen]  # what the place a person names shows
    found: abc.Callable[[abc.Sequence[db.Notification], bool], set[str]]
    """The lost lemons among these that run somewhere now, started by hand; unless the
    flag (a dry run) is set, their rows are pointed there and are lost no longer."""
    relink: abc.Callable[[bool], Relinked]
    """Point every active row at the pane its lemon runs in (only report it, on a dry
    run); a lost lemon found running is lost no longer."""
    unready: abc.Callable[[db.Notification], str]
    """Why a running lemon's recorded place couldn't be restored after a crash, or ""."""
    strays: abc.Callable[[], list[str]]
    """Running lemons the inbox has no row for, as a person names them."""
    advice: str  # where a person learns more about lemons it couldn't restore
    up: abc.Callable[[], bool]
    """Whether the terminal runs now. A restore started from the inbox puts lemons back
    only into a running one, and never starts the terminal itself."""


class _Attempt(ty.NamedTuple):
    window: str  # the window this attempt made, "" if it made none
    why: str  # why it failed to start, "" when the line was typed
    seen: report.Seen | None = None  # its window, as it was closed for not running the lemon


def _start(lemon: Lemon, terminal: Terminal) -> _Attempt:
    window, why = terminal.open(lemon.spot, lemon.launch.cwd, lemon.launch.environment)
    if why or not window:
        return _Attempt("", why or "its window could not be made")

    return _Attempt(window, terminal.type(window, lemon.launch.line))


def _await(
    lemons: abc.Sequence[Lemon], terminal: Terminal, seconds: float, poll: float
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
    lemons: abc.Sequence[Lemon], terminal: Terminal, seconds: float, poll: float
) -> tuple[set[str], dict[str, _Attempt]]:
    """Start *lemons*: the channels proven running, and each one's attempt.

    A lemon not proven running has the window this attempt made closed, and only that
    one, so nothing runs under its name but the lemon itself.
    """
    attempts = {lemon.channel: _start(lemon, terminal) for lemon in lemons}
    running = _await(
        [each for each in lemons if not attempts[each.channel].why], terminal, seconds, poll
    )
    for lemon in lemons:
        attempt = attempts[lemon.channel]
        if lemon.channel not in running and attempt.window:
            attempts[lemon.channel] = attempt._replace(seen=terminal.seen(lemon.spot.where))
            terminal.close(attempt.window)
    return running, attempts


def _failed(lemon: Lemon, terminal: Terminal, why: str, seen: report.Seen | None) -> report.Result:
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
    lemons: abc.Sequence[Lemon],
    terminal: Terminal,
    parallel: int,
    seconds: float,
    progress: abc.Callable[[str], None],
    poll: float = 1.0,
) -> tuple[list[Lemon], list[report.Result]]:
    """(the lemons proven running in their windows, a result for each that is not).

    *parallel* lemons start at once, and each batch is proven before the next starts.
    A lemon that fails is started once more.
    """
    started: list[Lemon] = []
    failed: list[report.Result] = []
    for at in range(0, len(lemons), parallel):
        batch = lemons[at : at + parallel]
        running, _ = _round(batch, terminal, seconds, poll)
        again = [lemon for lemon in batch if lemon.channel not in running]
        retried, attempts = _round(again, terminal, seconds, poll)
        running |= retried
        started += [lemon for lemon in batch if lemon.channel in running]
        failed += [
            _failed(lemon, terminal, attempts[lemon.channel].why, attempts[lemon.channel].seen)
            for lemon in again
            if lemon.channel not in running
        ]
        progress(f"{len(started)} of {len(lemons)} running, {len(failed)} not restored")
    return started, failed
