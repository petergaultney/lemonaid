"""The `gh` user's GitHub notification threads, read without marking any of them read.

`all=true` includes threads the user has already read or dismissed, so reading here never
depends on, or changes, how the user triages them. A thread's `reason` is the latest one
GitHub recorded for it, not every reason it has had.
"""

import typing as ty

from . import github_api


class Thread(ty.NamedTuple):
    id: str
    reason: str  # mention, author, comment, review_requested, team_mention...
    updated_at: str  # ISO 8601, UTC
    repo: str  # owner/name
    subject_type: str  # PullRequest, Issue, ...
    subject_url: str  # the API URL; empty for some subject types
    title: str

    @property
    def pr_number(self) -> int | None:
        if self.subject_type != "PullRequest" or "/pulls/" not in self.subject_url:
            return None

        return int(self.subject_url.rsplit("/", 1)[1])


def parse_thread(node: dict) -> Thread:
    subject = node.get("subject") or {}
    return Thread(
        str(node["id"]),
        node.get("reason") or "",
        node.get("updated_at") or "",
        (node.get("repository") or {}).get("full_name") or "",
        subject.get("type") or "",
        subject.get("url") or "",
        subject.get("title") or "",
    )


def fetch(since: str, *, participating: bool = False) -> list[Thread] | None:
    """Every thread updated at or after *since* (ISO 8601), read or not; None unless every
    page was read, so a failure is never taken for no news."""
    nodes = github_api.rest_pages(
        "notifications",
        {"all": "true", "participating": str(participating).lower(), "since": since},
        per_page=50,  # the most this endpoint returns
    )
    return None if nodes is None else [parse_thread(n) for n in nodes]
