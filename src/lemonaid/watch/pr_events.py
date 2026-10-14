"""Compare one PR snapshot with its durable cursors, committing after delivery."""

import json
import pathlib
import typing as ty

from . import cursors, delivery, merge_health, pr_activity, pr_comments


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


def events(
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


def poll(
    stem: pathlib.Path,
    pr: int,
    snap: pr_activity.Snapshot,
    deliver: delivery.Deliver,
    *,
    head: str = "",
    comments: bool = True,
    ci: bool = True,
    own_head: ty.Callable[[str], bool] = lambda head: False,
) -> bool:
    reported_path, review_path, merge_path, head_path = (
        stem.with_suffix(".reported.json"),
        stem.with_suffix(".review.json"),
        stem.with_suffix(".merge.json"),
        stem.with_suffix(".head.json"),
    )
    reported = _load_reported(reported_path)
    review = _load_review(review_path)
    seen = merge_health.load(merge_path) if merge_path.exists() else None
    saved_head = _load_head(head_path)
    sha, state = (head, saved_head[1] if saved_head else "OPEN") if head else saved_head or ("", "")
    if not sha:
        sha, state = snap.head, snap.state
    review = review or (snap.draft, snap.decision)
    candidates = {c.id: c for c in snap.comments} if comments else {}
    if reported is None:
        reported = set(candidates) if comments else set()
    if seen is None:
        seen = merge_health.events(pr, snap, merge_health.Seen("", ""), comments=comments, ci=ci)[1]
        seen = seen._replace(passed=seen.stable)
    blockers, now_seen = (
        merge_health.events(pr, snap, seen, comments=comments, ci=ci)
        if comments or ci
        else ([], seen)
    )
    changes = [
        *events(
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
    if changes:
        deliver("; ".join(changes))
    seen = now_seen
    merge_health.save(merge_path, seen)
    reported = reported | set(candidates)
    if comments:
        cursors.write_json(reported_path, sorted(reported))
    review = snap.draft, snap.decision
    cursors.write_json(review_path, {"draft": review[0], "decision": review[1]})
    if (snap.head, snap.state) != saved_head:
        saved_head = snap.head, snap.state
        cursors.write_json(head_path, {"head": snap.head, "state": snap.state})
    return bool(changes)
