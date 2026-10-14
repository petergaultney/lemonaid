"""Compare a repo's pull requests with what a lemon was last told, committing after delivery.

The cursor holds each open PR the lemon has seen (its draft flag, head and labels). The
first poll takes every open PR as seen. A PR is reported when it is opened ready for
review, marked ready, gains one of the watched labels, or closed or merged after being
seen; with `pushes`, also when a ready PR's head moves.
"""

import hashlib
import json
import pathlib
import typing as ty
from collections import abc

from . import cursors, delivery, repo_activity

Seen = dict[str, dict[str, ty.Any]]


def state_stem(state_dir: pathlib.Path, repo: str, me: str) -> pathlib.Path:
    key = repo.lower() + (f"\0{me}" if me else "")
    return state_dir / ("repo-" + hashlib.sha1(key.encode()).hexdigest()[:16])


def _entry(pr: repo_activity.PullRequest) -> dict[str, ty.Any]:
    return {"draft": pr.draft, "head": pr.head, "labels": sorted(pr.labels)}


def _describe(repo: str, pr: repo_activity.PullRequest) -> str:
    return f'{repo} PR #{pr.number} "{pr.title}" by {pr.author} ({pr.branch})'


def events(
    repo: str,
    seen: Seen | None,
    prs: abc.Iterable[repo_activity.PullRequest],
    labels: abc.Collection[str] = (),
    exclude_authors: abc.Collection[str] = (),
    pushes: bool = False,
) -> tuple[list[str], Seen]:
    """The lines to report and the cursor to save once they are delivered."""
    prs = list(prs)
    if seen is None:
        return [], {str(p.number): _entry(p) for p in prs if p.state == "OPEN"}

    wanted = {label.lower() for label in labels}
    skipped = {login.lower() for login in exclude_authors}
    now = dict(seen)
    lines: list[str] = []
    for pr in prs:
        key, old = str(pr.number), seen.get(str(pr.number))
        mine = {label.lower() for label in pr.labels}
        shown = pr.author.lower() not in skipped and (not wanted or bool(wanted & mine))
        if pr.state != "OPEN":
            if old is not None:
                now.pop(key)
                if shown:
                    lines.append(f"{_describe(repo, pr)} was {pr.state.lower()}")
            continue

        now[key] = _entry(pr)
        if not shown:
            continue

        added = sorted(wanted & mine - {label.lower() for label in (old or {}).get("labels", ())})
        if old is None:
            if not pr.draft:
                lines.append(f"{_describe(repo, pr)} was opened ready for review")
        elif old["draft"] and not pr.draft:
            lines.append(f"{_describe(repo, pr)} is now ready for review")
        elif pushes and not pr.draft and old["head"] != pr.head:
            lines.append(f"{_describe(repo, pr)} head moved {old['head'][:10]} -> {pr.head[:10]}")
        if old is not None and added:
            lines.append(f"{_describe(repo, pr)} got label {', '.join(added)}")
    return lines, now


def _load(path: pathlib.Path) -> Seen | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None

    return saved if isinstance(saved, dict) else None


def poll(
    stem: pathlib.Path,
    repo: str,
    prs: abc.Iterable[repo_activity.PullRequest],
    deliver: delivery.Deliver,
    *,
    labels: abc.Collection[str] = (),
    exclude_authors: abc.Collection[str] = (),
    pushes: bool = False,
) -> bool:
    """True if an event was delivered. A delivery that raises leaves the cursor unchanged."""
    path = stem.with_suffix(".seen.json")
    lines, now = events(repo, _load(path), prs, labels, exclude_authors, pushes)
    if lines:
        deliver("; ".join(lines))
    cursors.write_json(path, now)
    return bool(lines)
