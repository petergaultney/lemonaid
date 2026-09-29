"""One GraphQL snapshot of a PR: head, state, draft, review decision, and the review comments a lemon should answer.

Lemons post with the human's GitHub account, so authorship can't tell them apart; a body
starting with the lemon marker is a lemon's, anything else is a human's. Bots, pending
(unsubmitted) review comments, and resolved or outdated threads never count.
"""

import json
import subprocess
import typing as ty

LEMON_MARKER = "\N{LEMON}"
_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      state
      isDraft
      reviewDecision
      reviewThreads(last: 100) {
        nodes { isResolved isOutdated path line
          comments(last: 50) { nodes { id body state author { login __typename } } } }
      }
      reviews(last: 50) { nodes { id body state author { login __typename } } }
      comments(last: 100) { nodes { id body author { login __typename } } }
    }
  }
}
"""


class Comment(ty.NamedTuple):
    id: str
    where: str  # "path:line", "review", or "conversation"
    author: str
    body: str


class Snapshot(ty.NamedTuple):
    head: str
    state: str
    draft: bool
    decision: str  # APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED, or "" when GitHub gives none
    comments: list[Comment]  # human comments in the order GitHub returned them


def _is_human(node: dict) -> bool:
    author = node.get("author") or {}
    return (
        author.get("__typename") != "Bot"
        and node.get("state") != "PENDING"
        and bool(node["body"].strip())
        and not node["body"].lstrip().startswith(LEMON_MARKER)
    )


def _comment(node: dict, where: str) -> Comment:
    return Comment(
        node["id"], where, (node.get("author") or {}).get("login", "ghost"), node["body"]
    )


def _human_comments(pr: dict) -> ty.Iterator[Comment]:
    for t in pr["reviewThreads"]["nodes"]:
        if not t["isResolved"] and not t["isOutdated"]:
            where = f"{t['path']}:{t['line']}"
            yield from (_comment(c, where) for c in t["comments"]["nodes"] if _is_human(c))
    yield from (_comment(r, "review") for r in pr["reviews"]["nodes"] if _is_human(r))
    yield from (_comment(c, "conversation") for c in pr["comments"]["nodes"] if _is_human(c))


def fetch(repo: str, number: int) -> Snapshot | None:
    """None when gh fails - a transient failure must not end the wait."""
    owner, _, name = repo.partition("/")
    r = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
            "-f",
            f"query={_QUERY}",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None

    try:
        pr = json.loads(r.stdout)["data"]["repository"]["pullRequest"]
    except (ValueError, KeyError, TypeError):
        return None
    return Snapshot(
        pr["headRefOid"],
        pr["state"],
        pr["isDraft"],
        pr["reviewDecision"] or "",
        list(_human_comments(pr)),
    )


def gist(c: Comment) -> str:
    return f"{c.author} ({c.where}): {' '.join(c.body.split())[:100]}"
