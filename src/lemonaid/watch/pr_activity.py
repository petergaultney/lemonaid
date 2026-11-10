"""One GraphQL snapshot of a PR: head, state, draft, review decision, assignees and approving reviewers, the user's own verdict, mergeability, checks, unresolved threads, and the review comments a lemon should answer.

Lemons post with their human's GitHub account, so authorship can't tell them apart. Each
lemon signs right after the lemon marker (`🍋 StateJob (Reviewer): ...`), and a comment is
the watching lemon's own only when it carries one of its signatures. Every other comment,
including other lemons' and unsigned 🍋 ones, is someone else's. Bots, pending
(unsubmitted) review comments never count. Resolved and outdated threads count unless
the watcher explicitly skips them.
"""

import typing as ty
from collections import abc

from . import github_api, pr_comments, pr_reviewers, pr_threads

_ROLLUP = """
      statusCheckRollup { contexts(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on CheckRun { name status conclusion completedAt detailsUrl
            isRequired(pullRequestNumber: $number)
            annotations(first: 10) { nodes { path message annotationLevel location { start { line } } } } }
          ... on StatusContext { context state createdAt targetUrl isRequired(pullRequestNumber: $number) }
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
    visibility
    pullRequest(number: $number) {
      headRefOid
      baseRefName
      state
      isDraft
      reviewDecision
      mergeable"""
    + pr_reviewers.QUERY
    + """      commits(last: 1) { nodes { commit { oid"""
    + _ROLLUP
    + """} } }
      reviewThreads(last: 100) {
        nodes { isResolved isOutdated path line
          comments(last: 50) { nodes { id body state viewerDidAuthor authorAssociation author { login __typename } } } }
      }
      reviews(last: 50) { nodes { id body state authorAssociation author { login __typename } } }
      comments(last: 100) { nodes { id body authorAssociation author { login __typename } } }
    }
  }
}
"""
)


class Check(ty.NamedTuple):
    name: str
    required: bool
    outcome: ty.Literal["pending", "failed", "passed", "skipped"]
    finished: str = ""  # when this result was produced; a re-run gives a later one
    url: str = ""
    errors: tuple[str, ...] = ()  # failure annotations, as `path:line: message`


class Snapshot(ty.NamedTuple):
    head: str
    state: str
    draft: bool
    decision: str  # APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED, or "" when GitHub gives none
    comments: list[pr_comments.Comment]  # others' comments in the order GitHub returned them
    base: str
    mergeable: str  # MERGEABLE, CONFLICTING, or UNKNOWN while GitHub computes it
    checks: list[Check]  # on the head commit
    visibility: str = ""  # PUBLIC, PRIVATE or INTERNAL
    authored: bool = False  # by the GitHub account lemonaid reads as
    assigned: tuple[str, ...] | None = ()  # people other than the author; None if not fetched
    approved: tuple[str, ...] | None = ()  # by latest verdict; None if reviews were cut off
    objecting: tuple[str, ...] | None = ()  # latest verdict requests changes; likewise
    user_verdict: str | None = ""  # the user's account's latest review state; None if not read
    unresolved: tuple[str, ...] | None = ()  # each unresolved thread's last word, see pr_threads


_FAILED = frozenset(
    {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE", "ACTION_REQUIRED", "STALE"}
)

_PASSED = frozenset({"SUCCESS"})

_SKIPPED = frozenset({"NEUTRAL", "SKIPPED"})


def _error(annotation: dict) -> str:
    line = ((annotation.get("location") or {}).get("start") or {}).get("line")
    return f"{annotation['path']}{f':{line}' if line else ''}: {annotation['message']}"


def _check(node: dict) -> Check:
    if node["__typename"] == "CheckRun":
        name, result = node["name"], node["conclusion"] if node["status"] == "COMPLETED" else None
        finished, url = node.get("completedAt") or "", node.get("detailsUrl") or ""
        annotations = (node.get("annotations") or {}).get("nodes") or []
    else:
        name, result = (
            node["context"],
            None if node["state"] in ("PENDING", "EXPECTED") else node["state"],
        )
        finished, url, annotations = node.get("createdAt") or "", node.get("targetUrl") or "", []
    return Check(
        name,
        bool(node["isRequired"]),
        "passed"
        if result in _PASSED
        else "skipped"
        if result in _SKIPPED
        else "failed"
        if result in _FAILED
        else "pending",
        finished,
        url,
        tuple(_error(a) for a in annotations if a and a.get("annotationLevel") == "FAILURE"),
    )


def ci_passed(checks: abc.Sequence[Check]) -> bool:
    """Skipped checks neither pass nor fail CI, so skipped-only checks are not a pass."""
    return any(c.outcome == "passed" for c in checks) and all(
        c.outcome in ("passed", "skipped") for c in checks
    )


def _contexts(commit: dict) -> dict:
    """A commit's page of check contexts; empty before any check has started."""
    rollup = commit["statusCheckRollup"]
    return rollup["contexts"] if rollup else {"pageInfo": {"hasNextPage": False}, "nodes": []}


def _repository(repo: str, number: int, query: str, after: str, oid: str) -> dict | None:
    owner, _, name = repo.partition("/")
    data = github_api.graphql(
        [
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
            *(["-f", f"after={after}"] if after else []),
            *(["-f", f"oid={oid}"] if oid else []),
        ],
        query,
    )
    return (data or {}).get("repository")


def read(repo: str, number: int) -> dict | None:
    """The PR's `repository` with every page of its head's checks merged into the first.

    None when gh fails or GitHub reads are paused.
    """
    r = _repository(repo, number, _QUERY, "", "")
    if r is None:
        return None

    commit = r["pullRequest"]["commits"]["nodes"][0]["commit"]
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
    if commit["statusCheckRollup"]:
        commit["statusCheckRollup"]["contexts"] = {
            "pageInfo": {"hasNextPage": False},
            "nodes": nodes,
        }
    return r


def parse(
    r: dict,
    signatures: abc.Iterable[str],
    *,
    skip_outdated: bool = False,
    skip_resolved: bool = False,
) -> Snapshot:
    """Comments signed with one of `signatures` are left out as the watching lemon's own."""
    pr = r["pullRequest"]
    commit = pr["commits"]["nodes"][0]["commit"]
    return Snapshot(
        commit["oid"],  # the head the checks belong to
        pr["state"],
        pr["isDraft"],
        pr["reviewDecision"] or "",
        list(
            pr_comments.others(
                pr, tuple(signatures), skip_outdated=skip_outdated, skip_resolved=skip_resolved
            )
        ),
        pr["baseRefName"],
        pr["mergeable"],
        [_check(n) for n in _contexts(commit)["nodes"] if n],
        r.get("visibility") or "",
        bool(pr.get("viewerDidAuthor")),
        pr_reviewers.assigned(pr),
        pr_reviewers.verdicts(pr, "APPROVED"),
        pr_reviewers.verdicts(pr, "CHANGES_REQUESTED"),
        pr_reviewers.user_verdict(pr),
        pr_threads.unresolved(pr),
    )


def fetch(
    repo: str,
    number: int,
    signatures: abc.Iterable[str],
    *,
    skip_outdated: bool = False,
    skip_resolved: bool = False,
    source: abc.Callable[[str, int], dict | None] = read,
) -> Snapshot | None:
    """None when gh fails or GitHub reads are paused - a transient failure must not end the wait.

    `source` gives the raw `repository`, from GitHub by default.
    """
    r = source(repo, number)
    if r is None:
        return None

    return parse(r, signatures, skip_outdated=skip_outdated, skip_resolved=skip_resolved)
