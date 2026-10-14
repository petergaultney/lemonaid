"""Replaying a writer's recorded edits, so a waiter can tell whether they account for a change.

The waiter replays, in order, the transitions it has not yet consumed, starting from the
body it last reported, and adopts a changed body silently only when that chain reaches it.
"""

import pathlib
from collections import abc

from . import own_edits


def last_seq(own_root: pathlib.Path, writer: str, doc: pathlib.Path) -> int:
    return max((t[0] for t in own_edits.transitions(own_root, writer, doc)), default=0)


def chain_to(
    transitions: abc.Iterable[tuple[int, str, str]], consumed: int, start: str, goal: str
) -> int | None:
    """The last seq, if every transition after `consumed`, in order, chains from `start` and ends at `goal`.

    A transition that doesn't start where the previous one ended means someone else changed
    the doc in between, so nothing is accounted for.
    """
    current, last = start, consumed
    for seq, before, after in sorted(t for t in transitions if t[0] > consumed):
        if before != current:
            return None

        current, last = after, seq
    return last if current == goal and last > consumed else None


def settles(
    own_root: pathlib.Path,
    writer: str,
    doc: pathlib.Path,
    consumed: int,
    settled_body: str,
    body: str,
) -> int | None:
    """The seq through which the writer's own edits account for every change from `settled_body` to `body`."""
    return chain_to(
        own_edits.transitions(own_root, writer, doc),
        consumed,
        own_edits.body_digest(settled_body),
        own_edits.body_digest(body),
    )
