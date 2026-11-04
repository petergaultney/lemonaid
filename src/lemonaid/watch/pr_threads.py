"""Who spoke last in each of a PR's unresolved review threads.

Resolving a thread is how anyone records it as handled, so an unresolved thread is one
still open, whoever left the last word in it.
"""

from . import lemon_signature


def _last_word(thread: dict) -> str:
    """The lemon name signing the thread's last submitted comment, else `@login`; "" for a
    thread with none."""
    submitted = [c for c in thread["comments"]["nodes"] if c.get("state") != "PENDING"]
    if not submitted:
        return ""

    last = submitted[-1]
    return (
        lemon_signature.signer(last["body"])
        or f"@{(last.get('author') or {}).get('login', 'ghost')}"
    )


def unresolved(pr: dict) -> tuple[str, ...]:
    """One entry per unresolved thread among the fetched ones, in GitHub's order."""
    return tuple(
        who for t in pr["reviewThreads"]["nodes"] if not t["isResolved"] if (who := _last_word(t))
    )
