"""The stalls among a set of PRs: whose move it is, and whether that lemon has sat idle too long."""

import dataclasses
from collections import abc

from ..brief import status as brief_status
from ..watch import pr_activity, relay_comments
from . import move, pulls

# A brief on an open PR with one of these says why nothing is moving.
_EXPLAINED = frozenset({"blocked", "merge", "review", "running"})


@dataclasses.dataclass(frozen=True)
class Stall:
    channel: str  # the lemon that owes the move
    what: str
    idle: float  # seconds since it last did anything

    @property
    def line(self) -> str:
        return f"stuck {brief_status.age(self.idle).removesuffix(' ago')}: {self.what}"


def _last_writers(pull: pulls.Pull) -> tuple[bool, bool]:
    """Whether the author, and whether the reviewer, wrote last in some thread of the doc."""
    if pull.doc is None:
        return False, False

    try:
        last = set(relay_comments.last_authors(pull.doc.read_text()))
    except (OSError, UnicodeError):
        return False, False

    return (
        pull.author is not None and f"Author ({pull.author.name})" in last,
        pull.reviewer is not None and f"Reviewer ({pull.reviewer.name})" in last,
    )


def _owed(pull: pulls.Pull, snap: pr_activity.Snapshot) -> list[tuple[pulls.Lemon, str]]:
    """The lemons that owe a move on *pull*, each with the move."""
    author_last, reviewer_last = _last_writers(pull)
    number = pull.key[1]
    mover = move.whose(
        snap,
        author_wrote_last=author_last,
        reviewer_wrote_last=reviewer_last,
        reviewed_head=pull.reviewed_head,
    )
    if mover == "holder":
        return [
            (lemon, f"#{number} is {snap.state.lower()} but its brief isn't done")
            for lemon in pull.briefs
        ]

    owner = pull.reviewer if mover == "reviewer" else pull.author
    if owner is None or not mover:
        return []

    if mover == "Peter":
        return [(owner, f"Peter's move on #{number}; its brief should say `merge`")]

    return [(owner, f"{mover}'s move on #{number}")]


def find(
    found: abc.Iterable[pulls.Pull],
    snapshots: abc.Mapping[pulls.Key, pr_activity.Snapshot | None],
    now: float,
    minutes: float,
) -> list[Stall]:
    """The stalls among *found*; a PR with no snapshot yet is never one."""
    stalls = []
    for pull in found:
        snap = snapshots.get(pull.key)
        if snap is None:
            continue

        if snap.state == "OPEN" and any(lemon.status in _EXPLAINED for lemon in pull.briefs):
            continue

        stalls += [
            Stall(lemon.channel, what, now - lemon.since)
            for lemon, what in _owed(pull, snap)
            if not lemon.mid_turn and now - lemon.since > minutes * 60
        ]
    return stalls
