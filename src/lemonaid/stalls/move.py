"""Whose move it is on a PR, from facts already gathered."""

import typing as ty

from ..watch import pr_activity

Mover = ty.Literal["", "holder", "author", "reviewer", "user"]


def _ready_to_merge(snap: pr_activity.Snapshot) -> bool:
    return (
        not snap.draft
        and snap.decision == "APPROVED"
        and snap.mergeable == "MERGEABLE"
        and all(check.outcome == "passed" for check in snap.checks)
    )


def whose(
    snap: pr_activity.Snapshot,
    *,
    author_wrote_last: bool,
    reviewer_wrote_last: bool,
    reviewed_head: str,
) -> Mover:
    """Who owes the next step; "" when nothing says.

    "holder" is whichever brief still lists a merged or closed PR. A reviewer's last word
    on an approved, green PR is an acknowledgement, so the merge outranks it.
    """
    if snap.state != "OPEN":
        return "holder"

    if author_wrote_last or (reviewed_head and not snap.head.startswith(reviewed_head)):
        return "reviewer"

    if _ready_to_merge(snap):
        return "user"

    if snap.decision == "APPROVED" and any(check.outcome == "pending" for check in snap.checks):
        return ""  # cleared, and only CI is left to run

    return "author" if reviewer_wrote_last else ""
