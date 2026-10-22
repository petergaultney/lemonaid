"""Which PR events wake a lemon, by the role it holds on that PR.

The author fixes what goes wrong on its PR; its reviewer re-reviews pushes; the author's
parent hears about readiness through its children's Status and needs the PR itself only
when it merges or closes. `[watch.roles.<role>] wake` replaces a role's list.
"""

import typing as ty
from collections import abc

AUTHOR, REVIEWER, PARENT = "author", "reviewer", "parent"
ROLES = (AUTHOR, REVIEWER, PARENT)

STATE = "state"  # merged, closed or reopened
HEAD = "head"  # a push the lemon didn't make
READY = "ready"
DRAFT = "draft"  # back in draft
DECISION = "decision"  # GitHub review decision
COMMENTS = "comments"
CONFLICT = "conflict"
CI_FAILED = "ci-failed"
CI_PASSED = "ci-passed"  # only reported with --ci
KINDS = (STATE, HEAD, READY, DRAFT, DECISION, COMMENTS, CONFLICT, CI_FAILED, CI_PASSED)

DEFAULT_WAKE: dict[str, frozenset[str]] = {
    AUTHOR: frozenset(KINDS) - {READY},
    REVIEWER: frozenset({STATE, HEAD}),
    PARENT: frozenset({STATE}),
}


class Event(ty.NamedTuple):
    kind: str
    text: str


def wake(role: str, overrides: abc.Mapping[str, frozenset[str]]) -> frozenset[str]:
    return overrides.get(role, DEFAULT_WAKE[role])


def derive(explicit: str, me: str, reviews_own_output: bool, a_child_authors: bool) -> str:
    """A PR subscription's role: *explicit* (`--role`), else a reviewer's when it signs as one
    or the PR's review doc is the brief's own output, else a parent's when a child of the
    lemon authors the PR, else the author's."""
    if explicit:
        return explicit

    if me.startswith("Reviewer (") or reviews_own_output:
        return REVIEWER

    return PARENT if a_child_authors else AUTHOR
