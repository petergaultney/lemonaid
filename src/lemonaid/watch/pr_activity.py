"""One GraphQL snapshot of a PR: head, state, draft, review decision, mergeability, checks, and the review comments a lemon should answer.

Lemons post with their human's GitHub account, so authorship can't tell them apart. Each
lemon signs right after the lemon marker (`🍋 Reviewer (StateJob): ...`), and a comment is
the watching lemon's own only when it carries one of its signatures. Every other comment,
including other lemons' and unsigned 🍋 ones, is someone else's. Bots, pending
(unsubmitted) review comments, and resolved or outdated threads never count.
"""

import json
import subprocess
import typing as ty
from collections import abc

from . import lemon_signature

_ROLLUP = """
      statusCheckRollup { contexts(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on CheckRun { name status conclusion isRequired(pullRequestNumber: $number) }
          ... on StatusContext { context state isRequired(pullRequestNumber: $number) }
        }
      } }
"""
_CHECKS_QUERY = (  # later pages, pinned to the head commit so a push between pages can't mix two heads
    "query($owner: String!, $name: String!, $number: Int!, $after: String, $oid: GitObjectID!) {"
    " repository(owner: $owner, name: $name) { object(oid: $oid) { ... on Commit {"
    + _ROLLUP
    + "} } } }"
)
_QUERY = (
    """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      baseRefName
      state
      isDraft
      reviewDecision
      mergeable
      commits(last: 1) { nodes { commit { oid"""
    + _ROLLUP
    + """} } }
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
)


class Comment(ty.NamedTuple):
    id: str
    where: str  # "path:line", "review", or "conversation"
    author: str
    body: str


class Check(ty.NamedTuple):
    name: str
    required: bool
    outcome: ty.Literal["pending", "failed", "passed"]


class Snapshot(ty.NamedTuple):
    head: str
    state: str
    draft: bool
    decision: str  # APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED, or "" when GitHub gives none
    comments: list[Comment]  # others' comments in the order GitHub returned them
    base: str
    mergeable: str  # MERGEABLE, CONFLICTING, or UNKNOWN while GitHub computes it
    checks: list[Check]  # on the head commit


def _is_others(node: dict, signatures: tuple[str, ...]) -> bool:
    author = node.get("author") or {}
    return (
        author.get("__typename") != "Bot"
        and node.get("state") != "PENDING"
        and bool(node["body"].strip())
        and not lemon_signature.is_signed(node["body"], signatures)
    )


def _comment(node: dict, where: str) -> Comment:
    return Comment(
        node["id"], where, (node.get("author") or {}).get("login", "ghost"), node["body"]
    )


def _others_comments(pr: dict, signatures: tuple[str, ...]) -> ty.Iterator[Comment]:
    def others(nodes: list[dict]) -> list[dict]:
        return [n for n in nodes if _is_others(n, signatures)]

    for t in pr["reviewThreads"]["nodes"]:
        if not t["isResolved"] and not t["isOutdated"]:
            where = f"{t['path']}:{t['line']}"
            yield from (_comment(c, where) for c in others(t["comments"]["nodes"]))
    yield from (_comment(r, "review") for r in others(pr["reviews"]["nodes"]))
    yield from (_comment(c, "conversation") for c in others(pr["comments"]["nodes"]))


_FAILED = frozenset(
    {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE", "ACTION_REQUIRED", "STALE"}
)


def _check(node: dict) -> Check:
    if node["__typename"] == "CheckRun":
        name, result = node["name"], node["conclusion"] if node["status"] == "COMPLETED" else None
    else:
        name, result = (
            node["context"],
            None if node["state"] in ("PENDING", "EXPECTED") else node["state"],
        )
    return Check(
        name,
        bool(node["isRequired"]),
        "pending" if result is None else "failed" if result in _FAILED else "passed",
    )


def _contexts(commit: dict) -> dict:
    """A commit's page of check contexts; empty before any check has started."""
    rollup = commit["statusCheckRollup"]
    return rollup["contexts"] if rollup else {"pageInfo": {"hasNextPage": False}, "nodes": []}


def _repository(repo: str, number: int, query: str, after: str, oid: str) -> dict | None:
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
            *(["-f", f"after={after}"] if after else []),
            *(["-f", f"oid={oid}"] if oid else []),
            "-f",
            f"query={query}",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None

    try:
        return json.loads(r.stdout)["data"]["repository"]
    except (ValueError, KeyError, TypeError):
        return None


def fetch(repo: str, number: int, signatures: abc.Iterable[str]) -> Snapshot | None:
    """None when gh fails - a transient failure must not end the wait.

    Comments signed with one of `signatures` are left out as the watching lemon's own.
    """
    r = _repository(repo, number, _QUERY, "", "")
    if r is None:
        return None

    pr = r["pullRequest"]
    commit = pr["commits"]["nodes"][0]["commit"]
    page = _contexts(commit)
    nodes = list(page["nodes"])
    while page["pageInfo"]["hasNextPage"]:  # a PR can have over 100 checks
        more = _repository(
            repo, number, _CHECKS_QUERY, page["pageInfo"]["endCursor"], commit["oid"]
        )
        if more is None:
            return None

        page = _contexts(more["object"])
        nodes.extend(page["nodes"])
    return Snapshot(
        commit["oid"],  # the head the checks belong to
        pr["state"],
        pr["isDraft"],
        pr["reviewDecision"] or "",
        list(_others_comments(pr, tuple(signatures))),
        pr["baseRefName"],
        pr["mergeable"],
        [_check(n) for n in nodes if n],
    )


def gist(c: Comment) -> str:
    return f"{c.author} ({c.where}): {' '.join(c.body.split())[:100]}"
