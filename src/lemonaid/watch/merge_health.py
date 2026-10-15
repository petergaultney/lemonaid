"""Merge blockers a PR's author should fix before anyone asks: a conflict with its base branch, and failed CI.

Each is reported once per head commit. A conflict is reported when GitHub first says
CONFLICTING at a head, and again if the PR became mergeable in between; UNKNOWN (GitHub
still computing) changes nothing. CI is reported once no check on the head is still
running and any check has failed, whether or not it is required for merging. With `--ci`,
passing CI is also reported, only when every check has passed and the same set of checks
passed on the previous poll too (a workflow's jobs may not be queued
yet when the first ones finish); no checks is not completion. A pass is reported again if
the set of checks it covered later changes, so a premature one never hides the real one.
"""

import json
import pathlib
import typing as ty

from . import cursors, pr_activity


class Seen(ty.NamedTuple):
    conflict_head: str  # head last seen CONFLICTING; "" once seen MERGEABLE
    ci_head: str  # head whose CI failure was last reported
    stable: str = ""  # head and checks of the previous poll if all had passed, else ""
    passed: str = ""  # head and checks of the last reported pass


def load(path: pathlib.Path) -> Seen:
    try:
        saved = json.loads(path.read_text())
        return Seen(
            str(saved["conflict_head"]),
            str(saved["ci_head"]),
            str(saved.get("stable", "")),
            str(saved.get("passed", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return Seen("", "")


def save(path: pathlib.Path, seen: Seen) -> None:
    cursors.write_json(path, seen._asdict())


def _failed(checks: ty.Sequence[pr_activity.Check]) -> list[str]:
    """Names of all failed checks, or [] while any check is still running."""
    if any(c.outcome == "pending" for c in checks):
        return []

    return [c.name for c in checks if c.outcome == "failed"]


def _all_passed(snap: pr_activity.Snapshot) -> str:
    """Identifies the head and its set of checks once all have passed, else ""."""
    if not snap.checks or any(c.outcome != "passed" for c in snap.checks):
        return ""

    return snap.head + ":" + ",".join(sorted(c.name for c in snap.checks))


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
    now = _all_passed(snap)
    passed = ci and bool(now) and now == seen.stable and now != seen.passed
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
        snap.head if failed else seen.ci_head,
        now,
        now if passed else seen.passed,
    )
