"""Review comments eligible to wake a PR watcher."""

import json
import typing as ty
from collections import abc

from . import lemon_signature


class Comment(ty.NamedTuple):
    id: str
    where: str  # "path:line", "review", or "conversation"
    author: str
    body: str
    association: str = (
        ""  # GitHub's authorAssociation: OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, NONE...
    )


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
        node["id"],
        where,
        (node.get("author") or {}).get("login", "ghost"),
        node["body"],
        node.get("authorAssociation") or "",
    )


def others(
    pr: dict,
    signatures: tuple[str, ...],
    *,
    skip_outdated: bool = False,
    skip_resolved: bool = False,
) -> ty.Iterator[Comment]:
    def eligible(nodes: list[dict]) -> list[dict]:
        return [n for n in nodes if _is_others(n, signatures)]

    for t in pr["reviewThreads"]["nodes"]:
        if not (skip_resolved and t["isResolved"]) and not (skip_outdated and t["isOutdated"]):
            where = f"{t['path']}:{t['line']}"
            yield from (_comment(c, where) for c in eligible(t["comments"]["nodes"]))
    yield from (_comment(r, "review") for r in eligible(pr["reviews"]["nodes"]))
    yield from (_comment(c, "conversation") for c in eligible(pr["comments"]["nodes"]))


_INSIDERS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def is_trusted(c: Comment, trusted: abc.Set[str]) -> bool:
    """*trusted* holds the github.com logins, lowercased, the user has said to act on."""
    return c.author.lower() in trusted


def is_outsider(c: Comment, trusted: abc.Set[str]) -> bool:
    return c.association not in _INSIDERS and not is_trusted(c, trusted)


def gist(c: Comment, trusted: abc.Set[str] = frozenset()) -> str:
    label = ", ".join(
        [
            *([c.association] if c.association else []),
            *(["trusted"] if is_trusted(c, trusted) else []),
        ]
    )
    # Quoted, so a body can't read as another comment's author and label.
    body = json.dumps(" ".join(c.body.split())[:100], ensure_ascii=False)
    return f"{c.author}{f' [{label}]' if label else ''} ({c.where}): {body}"
