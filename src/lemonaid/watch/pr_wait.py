"""The waiting loop behind `lemonaid watch pr`, and the cursors it keeps between waiters.

The head and state, comments already reported, the draft flag and review decision, and
the heads whose conflict or CI result was reported, are remembered per PR in the lemon's
cursor directory (see cursors.py), so a push, merge or comment made while no waiter ran
is reported by the next one.
"""

import hashlib
import json
import pathlib
import sys
import time
import typing as ty

from . import cursors, delivery, merge_health, pr_activity, pr_comments


def state_stem(state_dir: pathlib.Path, repo: str, pr: int, me: str) -> pathlib.Path:
    key = f"{repo}#{pr}" + (f"\0{me}" if me else "")
    return state_dir / hashlib.sha1(key.encode()).hexdigest()[:16]


def _load_reported(path: pathlib.Path) -> set[str] | None:
    """Comment IDs already reported, or None with no saved state."""
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def _load_review(path: pathlib.Path) -> tuple[bool, str] | None:
    """(draft, decision) as last reported, or None with no saved state."""
    try:
        saved = json.loads(path.read_text())
        return bool(saved["draft"]), str(saved["decision"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _ci_hint(pr: int, snap: pr_activity.Snapshot) -> str:
    """Said once at arm time when checks are pending but a passing run would not wake us."""
    if snap.state != "OPEN" or not any(c.outcome == "pending" for c in snap.checks):
        return ""

    return f"PR #{pr} has checks pending; add --ci to be woken when CI passes"


def _events(
    pr: int,
    snap: pr_activity.Snapshot,
    sha: str,
    state: str,
    review: tuple[bool, str],
    new: list[pr_comments.Comment],
    own_head: ty.Callable[[str], bool],
) -> list[str]:
    draft, decision = review
    return [
        *([f"PR #{pr} is now {snap.state}"] if state and snap.state != state else []),
        *(
            [f"PR #{pr} head moved {sha[:10]} -> {snap.head[:10]}"]
            if sha and not snap.head.startswith(sha) and not own_head(snap.head)
            else []
        ),
        *(
            [f"PR #{pr} is back in draft" if snap.draft else f"PR #{pr} is now ready for review"]
            if snap.draft != draft
            else []
        ),
        *(
            [f"PR #{pr} review decision: {snap.decision or 'none'}"]
            if snap.decision != decision
            else []
        ),
        *(
            [
                f"PR #{pr}: {len(new)} new comment(s) - "
                + "; ".join(pr_comments.gist(c) for c in new[:3])
            ]
            if new
            else []
        ),
    ]


def _load_head(path: pathlib.Path) -> tuple[str, str] | None:
    """(head, state) as last reported, or None with no saved state."""
    try:
        saved = json.loads(path.read_text())
        return str(saved["head"]), str(saved["state"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


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
) -> None:
    """With `comments`, also reports a conflict with the base and failed CI (see merge_health).

    With `ci`, passing CI is also reported. `head`, when set, overrides the saved head.
    A move to a head `own_head` says the lemon pushed itself is not reported.
    Whatever has no saved cursor starts from the first snapshot, unreported; a waiter
    without `comments` saves no comment cursor, so a later one with it starts afresh.

    Raises `delivery.Failed` with the event unrecorded if `deliver` fails.
    """
    reported_path, review_path, merge_path, head_path = (
        stem.with_suffix(".reported.json"),
        stem.with_suffix(".review.json"),
        stem.with_suffix(".merge.json"),
        stem.with_suffix(".head.json"),
    )
    saved_reported = reported = _load_reported(reported_path)
    saved_review = review = _load_review(review_path)
    saved_seen = seen = merge_health.load(merge_path) if merge_path.exists() else None
    saved_head = _load_head(head_path)
    sha, state = (head, saved_head[1] if saved_head else "OPEN") if head else saved_head or ("", "")
    first = True
    hint = ""
    armed = False
    while True:
        if not first:
            time.sleep(interval)
        first = False
        snap = fetch()
        if snap is None:
            continue

        if not armed:
            armed = True
            hint = "" if ci else _ci_hint(pr, snap)
            if hint:
                print(hint, file=sys.stderr, flush=True)
        if not sha:
            sha, state = snap.head, snap.state
        review = review or (snap.draft, snap.decision)
        candidates = {c.id: c for c in snap.comments} if comments else {}
        if reported is None:
            reported = set(candidates) if comments else set()
        if seen is None:
            seen = merge_health.events(
                pr, snap, merge_health.Seen("", ""), comments=comments, ci=ci
            )[1]
        blockers, now_seen = (
            merge_health.events(pr, snap, seen, comments=comments, ci=ci)
            if comments or ci
            else ([], seen)
        )
        events = [
            *_events(
                pr,
                snap,
                sha,
                state,
                review,
                [c for i, c in candidates.items() if i not in reported],
                own_head,
            ),
            *blockers,
        ]
        if events:
            deliver("; ".join([*([hint] if hint else []), *events]))
            hint = ""
        seen = now_seen
        if seen != saved_seen:
            saved_seen = seen
            merge_health.save(merge_path, seen)
        reported = reported | set(candidates)
        if comments and reported != saved_reported:
            saved_reported = reported
            cursors.write_json(reported_path, sorted(reported))
        review = snap.draft, snap.decision
        if review != saved_review:
            saved_review = review
            cursors.write_json(review_path, {"draft": review[0], "decision": review[1]})
        if (snap.head, snap.state) != saved_head:
            saved_head = snap.head, snap.state
            cursors.write_json(head_path, {"head": snap.head, "state": snap.state})
        if events and once:
            return

        sha, state = snap.head, snap.state
