"""What a lemon needs to triage a notification thread: the subject's state and the user's part in it.

`acted` says whether the user's own account wrote, after the thread's latest activity, a
review or comment that doesn't start with the lemon marker: lemons post as the user and
start what they write with it, so any other is the user's own. GitHub doesn't notify you of your own
actions, so `updated_at` is the latest activity by someone else. Only each subject's
recent comments are read for this (`_RECENT`), which holds the user's latest unless a
long discussion followed it.

Subjects are read in GraphQL batches of `_BATCH`, a few batches at a time, since an
untriaged account can hold hundreds of threads.
"""

import typing as ty
from collections import abc
from concurrent import futures

from . import github_api, lemon_signature, notifications

_BATCH = 10
_READERS = 4
_TEXT = "createdAt viewerDidAuthor body"
_RECENT = f"comments(last: 30) {{ nodes {{ {_TEXT} }} }}"
_PR = f"""
  url state merged isDraft author {{ login }}
  viewerLatestReview {{ state submittedAt }}
  commits(last: 1) {{ nodes {{ commit {{ committedDate }} }} }}
  {_RECENT}
  reviews(last: 20) {{ nodes {{ submittedAt viewerDidAuthor body state }} }}
  reviewThreads(last: 20) {{ nodes {{ comments(last: 5) {{ nodes {{ {_TEXT} state }} }} }} }}
"""
_ISSUE = f"url state author {{ login }} {_RECENT}"


class Details(ty.TypedDict, total=False):
    thread_id: str
    repo: str
    reason: str
    type: str
    title: str
    updated_at: str
    unread: bool
    number: int
    html_url: str
    state: str  # open or closed
    merged: bool
    draft: bool
    author: str
    my_review: dict | None  # {"state", "submitted_at"} of the user's latest review
    latest_commit_at: str
    my_last_activity_at: str  # the user's latest unsigned review or comment
    acted: bool


def _subject(t: notifications.Thread) -> tuple[str, int] | None:
    if (number := t.pr_number) is not None:
        return "pullRequest", number

    if (number := t.issue_number) is not None:
        return "issue", number

    return None


def _query(threads: abc.Sequence[notifications.Thread]) -> str:
    parts = []
    for i, t in enumerate(threads):
        kind, number = _subject(t) or ("", 0)
        owner, name = t.repo.split("/", 1)
        fields = _PR if kind == "pullRequest" else _ISSUE
        parts.append(
            f't{i}: repository(owner: "{owner}", name: "{name}") '
            f"{{ {kind}(number: {number}) {{ {fields} }} }}"
        )
    return "query {\n" + "\n".join(parts) + "\n}"


def _texts(node: dict) -> abc.Iterator[dict]:
    yield from node["comments"]["nodes"]
    yield from (node.get("reviews") or {}).get("nodes") or ()
    for thread in (node.get("reviewThreads") or {}).get("nodes") or ():
        yield from thread["comments"]["nodes"]


def last_activity(node: dict) -> str:
    """When the user last wrote an unsigned comment or submitted review on the subject."""
    return max(
        (
            n.get("createdAt") or n.get("submittedAt") or ""
            for n in _texts(node)
            if n.get("viewerDidAuthor")
            and n.get("state") != "PENDING"
            and not (n.get("body") or "").lstrip().startswith(lemon_signature.LEMON_MARKER)
        ),
        default="",
    )


def details(t: notifications.Thread, node: dict | None) -> Details:
    """The thread with its subject's details; only the thread's own fields when the subject
    couldn't be read, or is neither a PR nor an issue."""
    own: Details = {
        "thread_id": t.id,
        "repo": t.repo,
        "reason": t.reason,
        "type": t.subject_type,
        "title": t.title,
        "updated_at": t.updated_at,
        "unread": t.unread,
    }
    if not node:
        return own

    last = last_activity(node)
    review = node.get("viewerLatestReview")
    commits = (node.get("commits") or {}).get("nodes") or []
    return {
        **own,
        "number": t.pr_number or t.issue_number or 0,
        "html_url": node.get("url") or "",
        "state": (node.get("state") or "").lower().replace("merged", "closed"),
        "merged": bool(node.get("merged")),
        "draft": bool(node.get("isDraft")),
        "author": (node.get("author") or {}).get("login") or "ghost",
        "my_review": (
            {"state": review["state"], "submitted_at": review["submittedAt"]} if review else None
        ),
        "latest_commit_at": commits[-1]["commit"]["committedDate"] if commits else "",
        "my_last_activity_at": last,
        "acted": bool(last) and last >= t.updated_at,
    }


def _batch(threads: abc.Sequence[notifications.Thread]) -> list[Details]:
    readable = [t for t in threads if _subject(t)]
    data = github_api.graphql([], _query(readable), partial=True) if readable else {}
    nodes = {
        t.id: ((data or {}).get(f"t{i}") or {}).get(_subject(t)[0])  # type: ignore[index]
        for i, t in enumerate(readable)
    }
    return [details(t, nodes.get(t.id)) for t in threads]


def describe(threads: abc.Sequence[notifications.Thread]) -> list[Details]:
    batches = [threads[i : i + _BATCH] for i in range(0, len(threads), _BATCH)]
    with futures.ThreadPoolExecutor(_READERS) as pool:
        return [d for found in pool.map(_batch, batches) for d in found]
