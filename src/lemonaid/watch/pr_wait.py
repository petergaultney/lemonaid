"""The waiting loop behind `lemonaid watch pr`, and the state it keeps between waiters.

Comments already reported, and the last reported draft flag and review decision, are
remembered per (PR, --me) in a state directory, by default $TMPDIR/watch-pr. The file
names match the standalone watch-pr.py, so the two share state and locks.
"""

import hashlib
import json
import pathlib
import tempfile
import time
import typing as ty

from . import delivery, pr_activity


def default_state_dir() -> pathlib.Path:
    return (
        pathlib.Path(tempfile.gettempdir()) / "watch-pr"
    )  # writable in Codex's sandbox; ~/.cache is not


def state_stem(state_dir: pathlib.Path, repo: str, pr: int, me: str) -> pathlib.Path:
    key = f"{repo}#{pr}" + (f"\0{me}" if me else "")
    return state_dir / hashlib.sha1(key.encode()).hexdigest()[:16]


def _load_reported(path: pathlib.Path) -> set[str]:
    try:
        return set(json.loads(path.read_text()))
    except (OSError, ValueError):
        return set()


def _load_review(path: pathlib.Path) -> tuple[bool, str] | None:
    """(draft, decision) as last reported, or None with no saved state."""
    try:
        saved = json.loads(path.read_text())
        return bool(saved["draft"]), str(saved["decision"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _events(
    pr: int,
    snap: pr_activity.Snapshot,
    sha: str,
    state: str,
    review: tuple[bool, str],
    new: list[pr_activity.Comment],
) -> list[str]:
    draft, decision = review
    return [
        *([f"PR #{pr} is now {snap.state}"] if state and snap.state != state else []),
        *(
            [f"PR #{pr} head moved {sha[:10]} -> {snap.head[:10]}"]
            if sha and snap.head != sha
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
                + "; ".join(pr_activity.gist(c) for c in new[:3])
            ]
            if new
            else []
        ),
    ]


def wait(
    fetch: ty.Callable[[], pr_activity.Snapshot | None],
    pr: int,
    interval: float,
    head: str,
    comments: bool,
    deliver: delivery.Deliver,
    once: bool,
    stem: pathlib.Path,
) -> None:
    """Raises `delivery.Failed` with the event unrecorded if `deliver` fails."""
    reported_path, review_path = (
        stem.with_suffix(".reported.json"),
        stem.with_suffix(".review.json"),
    )
    reported = _load_reported(reported_path)
    saved_review = review = _load_review(review_path)
    sha, state = head, "OPEN" if head else ""
    first = True
    while True:
        if not first:
            time.sleep(interval)
        first = False
        snap = fetch()
        if snap is None:
            continue

        if not sha:
            sha, state = snap.head, snap.state
        review = review or (snap.draft, snap.decision)
        candidates = {c.id: c for c in snap.comments} if comments else {}
        events = _events(
            pr, snap, sha, state, review, [c for i, c in candidates.items() if i not in reported]
        )
        if events:
            deliver("; ".join(events))
        if set(candidates) != reported:
            reported = set(candidates)
            reported_path.write_text(json.dumps(sorted(reported)))
        review = snap.draft, snap.decision
        if review != saved_review:
            saved_review = review
            review_path.write_text(json.dumps({"draft": review[0], "decision": review[1]}))
        if events and once:
            return

        sha, state = snap.head, snap.state
