"""Merge blockers a PR's author should fix before anyone asks: a conflict with its base branch, and failed CI.

Each is reported once per head commit. A conflict is reported when GitHub first says
CONFLICTING at a head, and again if the PR became mergeable in between; UNKNOWN (GitHub
still computing) changes nothing. CI is reported once no check on the head is still
running and a check that counts has failed. Required checks count when there are any;
otherwise (a PR stacked on another branch, a repo without branch protection) every check
does. With `--ci`, passing CI is also reported once per head; no checks is not completion.
A repo whose one required check gates on all the others gets one event naming
just that check.
"""

import json
import pathlib
import typing as ty

from . import pr_activity


class Seen(ty.NamedTuple):
    conflict_head: str  # head last seen CONFLICTING; "" once seen MERGEABLE
    ci_head: str  # head whose CI result was last reported


def load(path: pathlib.Path) -> Seen:
    try:
        saved = json.loads(path.read_text())
        return Seen(str(saved["conflict_head"]), str(saved["ci_head"]))
    except (OSError, ValueError, KeyError, TypeError):
        return Seen("", "")


def save(path: pathlib.Path, seen: Seen) -> None:
    path.write_text(json.dumps(seen._asdict()))


def _failed(checks: ty.Sequence[pr_activity.Check]) -> list[str]:
    """Names of the failed checks that count, or [] while any check is still running."""
    if any(c.outcome == "pending" for c in checks):
        return []

    return [c.name for c in ([c for c in checks if c.required] or checks) if c.outcome == "failed"]


def events(
    pr: int,
    snap: pr_activity.Snapshot,
    seen: Seen,
    *,
    comments: bool = True,
    ci: bool = False,
) -> tuple[list[str], Seen]:
    """Events to report for this snapshot, and what has now been seen."""
    if snap.state != "OPEN":
        return [], seen

    conflict = comments and snap.mergeable == "CONFLICTING" and seen.conflict_head != snap.head
    failed = _failed(snap.checks) if seen.ci_head != snap.head else []
    passed = (
        ci
        and seen.ci_head != snap.head
        and bool(snap.checks)
        and not any(c.outcome == "pending" for c in snap.checks)
        and not failed
    )
    return [
        *(
            [
                f"PR #{pr} conflicts with {snap.base} at {snap.head[:10]}: rebase onto origin/{snap.base}"
                " (if its base PR just merged, rebase only your commits, as watch-pr's stacked-PR step says),"
                f" run the tests, push --force-with-lease, check `gh pr view {pr} --json mergeable` is MERGEABLE,"
                " then tell your reviewer"
            ]
            if conflict
            else []
        ),
        *(
            [
                f"PR #{pr} CI failed at {snap.head[:10]}: {', '.join(failed[:5])}: read `gh pr checks {pr}`,"
                " fix it and push (or rerun a flaky job), then tell your reviewer"
            ]
            if failed
            else []
        ),
        *([f"PR #{pr} CI passed at {snap.head[:10]}"] if passed else []),
    ], Seen(
        {"CONFLICTING": snap.head, "MERGEABLE": ""}.get(snap.mergeable, seen.conflict_head)
        if comments
        else seen.conflict_head,
        snap.head if failed or passed else seen.ci_head,
    )
