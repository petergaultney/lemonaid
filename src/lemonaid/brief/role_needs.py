"""The waiters a lemon's roles require, and which of them aren't running."""

import dataclasses
import shlex
import sqlite3
from collections import abc
from pathlib import Path

from . import output_doc, roles, status


@dataclasses.dataclass(frozen=True)
class Need:
    kind: str  # `pr` or `doc`, as in the waiter registry
    target: str  # the registry's target: `owner/repo#12`, or an absolute path
    command: str  # without the harness's one-shot flag
    reason: str


def _me(role: str, lemon_id: str) -> str:
    return shlex.quote(f"{role} ({lemon_id.rsplit('.', 1)[-1]})")


def _pr(pr: roles.PR, me: str, reason: str, comments: bool) -> Need:
    return Need(
        "pr",
        f"{pr.repo}#{pr.number}",
        f"lemonaid watch pr --wait {pr.number} --repo {pr.repo} --me {me}"
        + (" --comments" if comments else ""),
        reason,
    )


def _doc(path: Path, me: str, reason: str) -> Need:
    resolved = path.resolve()

    return Need(
        "doc",
        str(resolved),
        f"lemonaid watch doc --wait {shlex.quote(str(resolved))} --me {me}",
        reason,
    )


def required(
    conn: sqlite3.Connection,
    lemon_id: str,
    text: str,
    is_open: abc.Callable[[roles.PR], bool],
) -> list[Need]:
    """The waiters *lemon_id*'s roles imply, for the open PRs among them."""
    if status.split(text).status == "done":
        return []

    needs: list[Need] = []
    own_doc = output_doc.read(text)
    if (reviewed := roles.reviewing(text)) and is_open(reviewed):
        me = _me("Reviewer", lemon_id)
        needs.append(_pr(reviewed, me, f"you review {reviewed.repo}#{reviewed.number}", False))
        if own_doc:
            needs.append(_doc(own_doc, me, "your review doc"))

    for pr in roles.authoring(text):
        if not is_open(pr):
            continue

        me = _me("Author", lemon_id)
        label = f"{pr.repo}#{pr.number}"
        needs.append(_pr(pr, me, f"you wrote {label}", True))
        needs.extend(
            _doc(doc, me, f"the review of {label}") for doc in roles.review_docs(conn, lemon_id, pr)
        )

    needs.extend(
        _doc(doc, _me("Lead", lemon_id), "a child's output doc")
        for doc in roles.child_docs(conn, lemon_id)
    )
    return list({(n.kind, n.target): n for n in needs}.values())


def missing(needs: abc.Iterable[Need], running: abc.Callable[[str, str], bool]) -> list[Need]:
    """The *needs* for which `running(kind, target)` is false."""
    return [need for need in needs if not running(need.kind, need.target)]
