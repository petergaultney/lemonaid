"""The open PRs requesting the `gh` user's review or assigned to them, in one GraphQL read.

Every lemon on a machine shares one `gh` user, so the result is saved per scope and a
read younger than the caller's interval is reused instead of asked again. Requests made
to a team the user belongs to are not included. Each search reads its first 100 PRs.
"""

import hashlib
import json
import os
import time
import typing as ty
from collections import abc
from pathlib import Path

from . import cursors, github_api

_FIELDS = "... on PullRequest { url number title author { login } repository { nameWithOwner } }"
_QUERY = f"""
query($requested: String!, $assigned: String!) {{
  requested: search(query: $requested, type: ISSUE, first: 100) {{ nodes {{ {_FIELDS} }} }}
  assigned: search(query: $assigned, type: ISSUE, first: 100) {{ nodes {{ {_FIELDS} }} }}
}}
"""


class PullRequest(ty.NamedTuple):
    url: str
    repo: str
    number: int
    title: str
    author: str
    requested: bool
    assigned: bool


def queries(scope: abc.Iterable[str]) -> tuple[str, str]:
    """The review-requested and assigned searches, limited to *scope* (`org:x`, `repo:o/n`)."""
    tail = " ".join(["is:open", "is:pr", "archived:false", *scope])
    return f"user-review-requested:@me {tail}", f"assignee:@me {tail}"


def parse(data: dict) -> list[PullRequest]:
    """One entry per PR, carrying whether it was found by each search."""
    found: dict[str, dict] = {}
    marks: dict[str, set[str]] = {}
    for search in ("requested", "assigned"):
        for node in (data.get(search) or {}).get("nodes") or ():
            if node and node.get("url"):
                found[node["url"]] = node
                marks.setdefault(node["url"], set()).add(search)
    return [
        PullRequest(
            url,
            node["repository"]["nameWithOwner"],
            node["number"],
            node["title"],
            (node["author"] or {}).get("login", "ghost"),
            "requested" in marks[url],
            "assigned" in marks[url],
        )
        for url, node in found.items()
    ]


def _snapshot_path(scope: abc.Sequence[str]) -> Path:
    key = hashlib.sha1("\0".join(scope).encode()).hexdigest()[:16]
    return github_api.state_dir() / "reviews" / f"{key}.json"


def _recent(path: Path, max_age: float) -> dict | None:
    try:
        if time.time() - path.stat().st_mtime >= max_age:
            return None

        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def fetch(scope: abc.Sequence[str], max_age: float) -> list[PullRequest] | None:
    """None when gh fails or GitHub reads are paused - a transient failure must not end the wait."""
    path = _snapshot_path(scope)
    with github_api.locked(path.with_suffix(".lock")):
        if (data := _recent(path, max_age)) is None:
            requested, assigned = queries(scope)
            data = github_api.graphql(
                ["-f", f"requested={requested}", "-f", f"assigned={assigned}"], _QUERY
            )
            if data is None:
                return None

            cursors.write_json(path, data)
            os.utime(path)  # write_json skips unchanged content, and the mtime is the read's age
    return parse(data)
