"""Compare the PRs asking for the user's review with what a lemon was last told.

The cursor holds, per PR URL, whether its review is requested and whether it is assigned.
The first poll takes every current PR as seen, unless `backlog` asks for them. A PR is
reported when its review is newly requested (again, after a review cleared the request)
or when it newly appears assigned without a request. Assignment added to a PR already
requested is not reported again.
"""

import hashlib
import json
import pathlib
from collections import abc

from . import cursors, delivery, review_requests

Seen = dict[str, dict[str, bool]]


def state_stem(state_dir: pathlib.Path, scope: abc.Sequence[str], me: str) -> pathlib.Path:
    key = "\0".join(scope).lower() + (f"\0\0{me}" if me else "")
    return state_dir / ("reviews-" + hashlib.sha1(key.encode()).hexdigest()[:16])


def _describe(pr: review_requests.PullRequest, why: str) -> str:
    return f'{pr.repo} PR #{pr.number} "{pr.title}" by {pr.author} {why}: {pr.url}'


def events(
    seen: Seen | None, prs: abc.Iterable[review_requests.PullRequest], backlog: bool = False
) -> tuple[list[str], Seen]:
    """The lines to report and the cursor to save once they are delivered."""
    prs = list(prs)
    now = {p.url: {"requested": p.requested, "assigned": p.assigned} for p in prs}
    if seen is None and not backlog:
        return [], now

    lines = []
    for pr in prs:
        old = (seen or {}).get(pr.url)
        if pr.requested and not (old or {}).get("requested"):
            lines.append(_describe(pr, "requests your review"))
        elif pr.assigned and old is None:
            lines.append(_describe(pr, "is assigned to you"))
    return lines, now


def _load(path: pathlib.Path) -> Seen | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    return saved if isinstance(saved, dict) else None


def poll(
    stem: pathlib.Path,
    prs: abc.Iterable[review_requests.PullRequest],
    deliver: delivery.Deliver,
    backlog: bool = False,
) -> bool:
    """True if an event was delivered. A delivery that raises leaves the cursor unchanged."""
    path = stem.with_suffix(".seen.json")
    lines, now = events(_load(path), prs, backlog)
    if lines:
        deliver("; ".join(lines))
    cursors.write_json(path, now)
    return bool(lines)
