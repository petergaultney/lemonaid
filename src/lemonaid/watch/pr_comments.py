"""Review comments eligible to wake a PR watcher."""

import typing as ty

from . import lemon_signature


class Comment(ty.NamedTuple):
    id: str
    where: str  # "path:line", "review", or "conversation"
    author: str
    body: str


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


def gist(c: Comment) -> str:
    return f"{c.author} ({c.where}): {' '.join(c.body.split())[:100]}"
