"""Whether each restored lemon came back to work, waited for up to a deadline.

A window with a harness in it is not a lemon at work: Codex can stop at a
dialog, or update itself and exit to the shell. The inbox is the evidence a
prompted lemon took its turn, and the terminal is the evidence of what went
wrong when it didn't.
"""

import time
import typing as ty
from collections import abc

from ..launch import window

PROMPTED = "prompted"
WORKING = "working"
STUCK = "stuck"
EXITED = "exited"
NO_BRIEF = "no brief"
NOTHING_TO_REARM = "nothing to rearm"
BY_HAND = "rearm by hand"  # its brief lists waiters, but its harness can't be started on a prompt
NOT_RESTORED = "not restored"

OK = frozenset({WORKING, NO_BRIEF, NOTHING_TO_REARM})

# A pane has a shell and nothing else until the shell starts the typed line.
_GRACE_SECONDS = 15.0
_TAIL_LINES = 2
_TAIL_WIDTH = 80


class Placed(ty.NamedTuple):
    channel: str
    name: str
    where: str  # the terminal's handle for the lemon's pane
    rearm: str  # PROMPTED, NO_BRIEF, NOTHING_TO_REARM or BY_HAND


class Seen(ty.NamedTuple):
    running: bool  # something other than the shell runs in the pane
    screen: str


class Result(ty.NamedTuple):
    channel: str
    name: str
    where: str
    outcome: str
    detail: str


def _tail(screen: str) -> str:
    lines = [line.strip() for line in screen.splitlines() if line.strip()][-_TAIL_LINES:]
    return " | ".join(
        line if len(line) <= _TAIL_WIDTH else line[: _TAIL_WIDTH - 3] + "..." for line in lines
    )


def _detail(seen: Seen) -> str:
    return window.dialog_in(seen.screen) or _tail(seen.screen)


def _settled(lemon: Placed, active: bool, seen: Seen, elapsed: float) -> Result | None:
    """*lemon*'s result if it can be known now, else None."""
    if lemon.rearm == PROMPTED and active:
        return Result(lemon.channel, lemon.name, lemon.where, WORKING, "")

    if not seen.running and elapsed >= _GRACE_SECONDS:
        return Result(lemon.channel, lemon.name, lemon.where, EXITED, _detail(seen))

    return None


def _final(lemon: Placed, seen: Seen) -> Result:
    """*lemon*'s result once the deadline has passed without it settling."""
    if not seen.running:
        return Result(lemon.channel, lemon.name, lemon.where, EXITED, _detail(seen))

    if lemon.rearm != PROMPTED:
        return Result(lemon.channel, lemon.name, lemon.where, lemon.rearm, "")

    return Result(lemon.channel, lemon.name, lemon.where, STUCK, _detail(seen))


def wait(
    lemons: abc.Sequence[Placed],
    started: float,
    deadline: float,
    activity: abc.Callable[[], abc.Mapping[str, float]],
    inspect: abc.Callable[[str], Seen],
    progress: abc.Callable[[str], None],
    poll: float = 5.0,
) -> list[Result]:
    """Each lemon's result, in *lemons*' order.

    *activity* gives each channel's latest inbox time, *inspect* what the
    terminal shows at a lemon's handle. A prompted lemon is working once the
    inbox hears from it after *started*; the rest settle only when they exit.
    """
    settled: dict[str, Result] = {}
    while True:
        now = time.time()
        latest = activity()
        for lemon in lemons:
            if lemon.channel not in settled:
                active = latest.get(lemon.channel, 0.0) > started
                if result := _settled(lemon, active, inspect(lemon.where), now - started):
                    settled[lemon.channel] = result

        waiting = [
            lemon for lemon in lemons if lemon.channel not in settled and lemon.rearm == PROMPTED
        ]
        if not waiting or now >= deadline:
            break

        progress(
            f"{sum(r.outcome == WORKING for r in settled.values())}/{len(lemons)} working, "
            f"{sum(r.outcome == EXITED for r in settled.values())} exited, "
            f"waiting on {len(waiting)} ({int(deadline - now)}s left)"
        )
        time.sleep(poll)

    return [settled.get(lemon.channel) or _final(lemon, inspect(lemon.where)) for lemon in lemons]


def describe(results: abc.Iterable[Result]) -> list[str]:
    """One line per lemon, for a person deciding which ones need a hand."""
    return [
        f"{r.outcome:<16} {r.where:<24} {r.name}" + (f"  ({r.detail})" if r.detail else "")
        for r in results
    ]
