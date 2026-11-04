"""Who spoke last in each of a PR's unresolved review threads.

Resolving a thread is how anyone records it as handled, so an unresolved thread is one
still open, whoever left the last word in it. Lemons post through the user's account, so
only a comment's signature tells a lemon's word from the user's.
"""

from . import lemon_signature


def _last_word(thread: dict) -> str | None:
    """`user LOGIN [SIGNER]` when the user's account wrote the thread's last submitted
    comment, else `other LOGIN [SIGNER]`; SIGNER is the lemon name signing it, if any. ""
    for a thread with no submitted comment; None for a snapshot cached before the query
    asked whose account wrote each comment."""
    submitted = [c for c in thread["comments"]["nodes"] if c.get("state") != "PENDING"]
    if not submitted:
        return ""

    last = submitted[-1]
    if "viewerDidAuthor" not in last:
        return None

    account = "user" if last["viewerDidAuthor"] else "other"
    login = (last.get("author") or {}).get("login", "ghost")
    return " ".join(w for w in (account, login, lemon_signature.signer(last["body"])) if w)


def unresolved(pr: dict) -> tuple[str, ...] | None:
    """One entry per unresolved thread among the fetched ones, in GitHub's order; None when
    any entry can't be told."""
    found = [_last_word(t) for t in pr["reviewThreads"]["nodes"] if not t["isResolved"]]
    return None if None in found else tuple(w for w in found if w)
