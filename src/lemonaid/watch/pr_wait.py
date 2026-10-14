"""The waiting loop behind `lemonaid watch pr`, and the cursors it keeps between waiters.

The head and state, comments already reported, the draft flag and review decision, and
the heads whose conflict or CI result was reported, are remembered per PR in the lemon's
cursor directory (see cursors.py), so a push, merge or comment made while no waiter ran
is reported by the next one.
"""

import hashlib
import pathlib
import sys
import time
import typing as ty
from collections import abc

from . import delivery, pr_activity, pr_events


def state_stem(state_dir: pathlib.Path, repo: str, pr: int, me: str) -> pathlib.Path:
    key = f"{repo}#{pr}" + (f"\0{me}" if me else "")
    return state_dir / hashlib.sha1(key.encode()).hexdigest()[:16]


def _ci_hint(pr: int, snap: pr_activity.Snapshot) -> str:
    """Said once at arm time when checks are pending but a passing run would not wake us."""
    if snap.state != "OPEN" or not any(c.outcome == "pending" for c in snap.checks):
        return ""

    return f"PR #{pr} has checks pending; add --ci to be woken when CI passes"


def wait(
    fetch: ty.Callable[[], pr_activity.Snapshot | None],
    pr: int,
    interval: float,
    head: str,
    comments: bool,
    deliver: delivery.Deliver,
    once: bool,
    stem: pathlib.Path,
    *,
    ci: bool = False,
    own_head: ty.Callable[[str], bool] = lambda head: False,
    trusted: abc.Set[str] = frozenset(),
) -> None:
    """With `comments`, also reports a conflict with the base and failed CI (see merge_health).

    With `ci`, passing CI is also reported. `head`, when set, overrides the saved head.
    A move to a head `own_head` says the lemon pushed itself is not reported.
    Whatever has no saved cursor starts from the first snapshot, unreported; a waiter
    without `comments` saves no comment cursor, so a later one with it starts afresh.

    Raises `delivery.Failed` with the event unrecorded if `deliver` fails.
    """
    first = True
    armed, hint = False, ""
    while True:
        if not first:
            time.sleep(interval)
        first = False
        snap = fetch()
        if snap is None:
            continue

        if not armed:
            armed = True
            hint = _ci_hint(pr, snap) if not ci else ""
            if hint:
                print(hint, file=sys.stderr, flush=True)
        changed = pr_events.poll(
            stem,
            pr,
            snap,
            lambda message, hint=hint: deliver("; ".join([hint, message]) if hint else message),
            head=head,
            comments=comments,
            ci=ci,
            own_head=own_head,
            trusted=trusted,
        )
        head = ""
        if changed:
            hint = ""
        if changed and once:
            return
