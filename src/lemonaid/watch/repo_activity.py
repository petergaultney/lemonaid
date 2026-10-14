"""One GraphQL read of a repo's pull requests: every open one, and the most recently closed."""

import json
import subprocess
import typing as ty

_FIELDS = """number title isDraft state headRefName headRefOid author { login }
  labels(first: 30) { nodes { name } }"""
_QUERY = (
    """
query($owner: String!, $name: String!, $after: String, $first: Boolean!) {
  repository(owner: $owner, name: $name) {
    open: pullRequests(states: OPEN, first: 100, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { """
    + _FIELDS
    + """ }
    }
    closed: pullRequests(states: [CLOSED, MERGED], first: 30, orderBy: {field: UPDATED_AT, direction: DESC}) @include(if: $first) {
      nodes { """
    + _FIELDS
    + """ }
    }
  }
}
"""
)
_MAX_PAGES = 10


class PullRequest(ty.NamedTuple):
    number: int
    title: str
    author: str
    branch: str
    head: str
    draft: bool
    state: str  # OPEN, CLOSED or MERGED
    labels: tuple[str, ...]


def _pull_request(node: dict) -> PullRequest:
    return PullRequest(
        node["number"],
        node["title"],
        (node["author"] or {}).get("login", "ghost"),
        node["headRefName"],
        node["headRefOid"],
        node["isDraft"],
        node["state"],
        tuple(label["name"] for label in node["labels"]["nodes"]),
    )


def _read(owner: str, name: str, after: str) -> dict | None:
    try:
        r = subprocess.run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={name}",
                "-F",
                f"first={'false' if after else 'true'}",
                *(["-f", f"after={after}"] if after else []),
                "-f",
                f"query={_QUERY}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None

    if r.returncode != 0:
        return None

    try:
        return json.loads(r.stdout)["data"]["repository"]
    except (ValueError, KeyError, TypeError):
        return None


def parse(pages: list[dict]) -> list[PullRequest]:
    """The open pull requests of every page, then the closed ones from the first."""
    return [
        *(_pull_request(n) for page in pages for n in page["open"]["nodes"] if n),
        *(_pull_request(n) for n in pages[0].get("closed", {"nodes": []})["nodes"] if n),
    ]


def fetch(repo: str) -> list[PullRequest] | None:
    """None when gh fails or the repo is unreadable - a transient failure must not end the wait."""
    owner, _, name = repo.partition("/")
    pages: list[dict] = []
    after = ""
    while len(pages) < _MAX_PAGES:
        page = _read(owner, name, after)
        if page is None:
            return None

        pages.append(page)
        info = page["open"]["pageInfo"]
        if not info["hasNextPage"]:
            break

        after = info["endCursor"]
    return parse(pages)
