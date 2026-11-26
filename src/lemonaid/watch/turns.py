"""A lemon's latest turn, for harnesses whose own file writes no hook can record (OpenClaw).

Where a waiter can ask whether its lemon is mid-turn, it holds every event until the turn ends,
and records a body change it sees appear during a turn as the lemon's own edit (own_edits).
"""

import typing as ty
from collections import abc

SLACK = 2.0  # seconds either side of a turn, for the gateway's and the file system's clocks


class Turn(ty.NamedTuple):
    running: bool  # also while it waits in the session's queue
    started: float  # epoch seconds; 0 when the harness doesn't say
    ended: float


Turns = abc.Callable[[], Turn | None]  # None when the harness can't say


def idle(turns: Turns | None) -> bool:
    """Whether a batch may go now: the lemon is not mid-turn, or nobody can tell."""
    turn = turns() if turns else None
    return not (turn and turn.running)


def overlaps(turn: Turn, since: float, until: float) -> bool:
    """Whether a change made at some time between *since* and *until* may have been made in *turn*."""
    if turn.started - SLACK > until:
        return False

    return turn.running or since <= turn.ended + SLACK
