"""The comments on one PR that directly mention the `gh` user, written by someone else.

A direct mention is `@login` outside quoted lines and code; `@org/team` is a team mention
and does not count. Comments by the user's own account are skipped: lemons post as the
user. So are bots and pending reviews.
"""

import re
import typing as ty
from collections import abc

from . import github_api

_FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
_CODE = re.compile(r"`[^`\n]*`")


class Mention(ty.NamedTuple):
    id: str
    url: str
    author: str
    where: str  # "path:line", "review", "conversation" or "description"
    body: str
    created_at: str  # ISO 8601, UTC


class Pull(ty.NamedTuple):
    login: str  # the gh user's
    title: str
    texts: tuple[Mention, ...]  # everything read, mentioning or not


def mentions_login(body: str, login: str) -> bool:
    prose = _CODE.sub("", _FENCE.sub("", body))
    unquoted = "\n".join(line for line in prose.splitlines() if not line.lstrip().startswith(">"))
    return bool(re.search(rf"(?<![\w@/.-])@{re.escape(login)}(?![\w/-])", unquoted, re.IGNORECASE))


def _text(node: dict, kind: str, where: str) -> Mention | None:
    user = node.get("user") or {}
    if user.get("type") == "Bot" or node.get("state") == "PENDING":
        return None

    return Mention(
        f"{kind}:{node.get('id')}",
        node.get("html_url") or "",
        user.get("login") or "ghost",
        where,
        node.get("body") or "",
        node.get("created_at") or node.get("submitted_at") or "",
    )


def _inline(node: dict) -> str:
    return f"{node.get('path')}:{node.get('line') or node.get('original_line') or '?'}"


def parse(
    login: str, pr: dict, comments: list[dict], reviews: list[dict], inline: list[dict]
) -> Pull:
    texts = [
        _text(pr, "pr", "description"),
        *(_text(n, "comment", "conversation") for n in comments),
        *(_text(n, "review", "review") for n in reviews),
        *(_text(n, "inline", _inline(n)) for n in inline),
    ]
    return Pull(login, pr.get("title") or "", tuple(m for m in texts if m))


def read(repo: str, number: int, since: str) -> Pull | None:
    """The PR's description, its reviews, and its comments updated at or after *since*,
    every page of each; None if any read fails. REST's `since` covers a reply on an old
    review thread, which a bounded GraphQL connection can leave out."""
    base = f"repos/{repo}"
    login = github_api.login()
    pr = github_api.rest(f"{base}/pulls/{number}")
    comments = github_api.rest_pages(f"{base}/issues/{number}/comments", {"since": since})
    inline = github_api.rest_pages(f"{base}/pulls/{number}/comments", {"since": since})
    reviews = github_api.rest_pages(f"{base}/pulls/{number}/reviews", {})
    if login is None or not isinstance(pr, dict) or None in (comments, inline, reviews):
        return None

    return parse(login, pr, comments or [], reviews or [], inline or [])


def direct(pull: Pull, since: str) -> abc.Iterator[Mention]:
    """The texts created at or after *since* (ISO 8601) that mention the user directly."""
    for m in pull.texts:
        if (
            m.created_at >= since
            and m.author.lower() != pull.login.lower()
            and mentions_login(m.body, pull.login)
        ):
            yield m
