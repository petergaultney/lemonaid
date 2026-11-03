"""Merge blockers a PR's author should fix before anyone asks: a conflict with its base branch, and failed CI.

Each is reported once per head commit, except that a CI failure is reported again when a re-run fails again. A conflict is reported when GitHub first says
CONFLICTING at a head, and again if the PR became mergeable in between; UNKNOWN (GitHub
still computing) changes nothing. CI is reported once no check on the head is still
running and any check has failed, whether or not it is required for merging. With `--ci`,
passing CI is also reported, only when every check has passed and the same set of checks
passed on the previous poll too (a workflow's jobs may not be queued
yet when the first ones finish); no checks is not completion. A pass is reported again if
the set of checks it covered later changes, so a premature one never hides the real one.
Without `--ci`, a stable pass is still reported, as `ci-green`, when the watcher last saw
CI unfinished, failed or not yet started, on this head or an earlier one (a push whose CI
finishes between polls), and the PR is not a draft, so an
author that cleared its `merge` status while CI ran hears that it can restore it.
"""

import json
import pathlib
import re
import typing as ty

from . import cursors, pr_activity, roles


class Seen(ty.NamedTuple):
    conflict_head: str  # head last seen CONFLICTING; "" once seen MERGEABLE
    ci_head: str  # head and failed checks (with finish times) last reported
    stable: str = ""  # head and checks of the previous poll if all had passed, else ""
    passed: str = ""  # head and checks of the last reported pass
    awaiting: str = ""  # head last seen without a passing set of checks; "" once one settles


def load(path: pathlib.Path) -> Seen:
    try:
        saved = json.loads(path.read_text())
        return Seen(
            str(saved["conflict_head"]),
            str(saved["ci_head"]),
            str(saved.get("stable", "")),
            str(saved.get("passed", "")),
            str(saved.get("awaiting", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return Seen("", "")


def save(path: pathlib.Path, seen: Seen) -> None:
    cursors.write_json(path, seen._asdict())


def _failed(checks: ty.Sequence[pr_activity.Check]) -> list[pr_activity.Check]:
    """All failed checks, or [] while any check is still running."""
    if any(c.outcome == "pending" for c in checks):
        return []

    return [c for c in checks if c.outcome == "failed"]


_EXIT_CODE = re.compile(r"Process completed with exit code \d+\.?$")  # says nothing new
_JOB = re.compile(r"/job/(\d+)")
_SHOWN = 3  # errors per check
_WIDTH = 300  # characters per error


def _detail(check: pr_activity.Check) -> str:
    errors = [" ".join(e.split())[:_WIDTH] for e in check.errors if not _EXIT_CODE.search(e)]
    job = _JOB.search(check.url)
    return "".join(
        [
            f"\n- {check.name}",
            *([f" ({check.url})"] if check.url else []),
            *(f"\n  - {e}" for e in errors[:_SHOWN]),
            *([f"\n  - and {len(errors) - _SHOWN} more"] if len(errors) > _SHOWN else []),
            *(
                [f"\n  - its log: `gh run view --job {job[1]} --log-failed`"]
                if job and not errors
                else []
            ),
        ]
    )


def _failure_id(head: str, failed: ty.Sequence[pr_activity.Check]) -> str:
    return head + ":" + ",".join(sorted(f"{c.name}@{c.finished}" for c in failed))


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
) -> tuple[list[roles.Event], Seen]:
    """Events to report for this snapshot, and what has now been seen."""
    if snap.state != "OPEN":
        return [], seen

    conflict = comments and snap.mergeable == "CONFLICTING" and seen.conflict_head != snap.head
    failed = _failed(snap.checks)
    failure = _failure_id(snap.head, failed) if failed else ""
    failed = failed if failure != seen.ci_head else []
    now = _all_passed(snap)
    settled = bool(now) and now == seen.stable
    green = settled and bool(seen.awaiting) and not snap.draft
    passed = ci and settled and now != seen.passed and not green
    return [
        *(
            [
                roles.Event(
                    roles.CONFLICT,
                    f"PR #{pr} conflicts with {snap.base} at {snap.head[:10]}: rebase onto origin/{snap.base}"
                    " (if its base PR just merged, rebase only your commits, as watch-pr's stacked-PR step says),"
                    f" run the tests, push --force-with-lease, check `gh pr view {pr} --json mergeable` is MERGEABLE,"
                    " then tell your reviewer",
                )
            ]
            if conflict
            else []
        ),
        *(
            [
                roles.Event(
                    roles.CI_FAILED,
                    f"PR #{pr} CI failed at {snap.head[:10]}: clear a `merge` status, fix it and push"
                    " (or rerun a flaky job), then tell your reviewer. Failed:"
                    + "".join(_detail(c) for c in failed[:5])
                    + (f"\n- and {len(failed) - 5} more" if len(failed) > 5 else ""),
                )
            ]
            if failed
            else []
        ),
        *(
            [
                roles.Event(
                    roles.CI_GREEN,
                    f"PR #{pr} CI passed at {snap.head[:10]}: check"
                    f" `gh pr view {pr} --json mergeable,reviewDecision,isDraft`;"
                    " if only your user's merge remains, set your brief's Status back to `merge`",
                )
            ]
            if green
            else []
        ),
        *(
            [roles.Event(roles.CI_PASSED, f"PR #{pr} CI passed at {snap.head[:10]}")]
            if passed
            else []
        ),
    ], Seen(
        {"CONFLICTING": snap.head, "MERGEABLE": ""}.get(snap.mergeable, seen.conflict_head)
        if comments
        else seen.conflict_head,
        failure if failed else seen.ci_head,
        now,
        now if passed or green else seen.passed,
        "" if settled else seen.awaiting if now else snap.head,
    )
