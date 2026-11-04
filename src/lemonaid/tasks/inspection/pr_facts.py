"""Facts about a GitHub PR, from the scout host's snapshot of it."""

from collections import abc

from ... import pr_url
from ...watch import pr_activity
from . import live

_FIELDS = (
    "checks",
    "draft",
    "head",
    "state",
    "mergeable",
    "authored",
    "assigned",
    "approved",
    "objecting",
    "user_verdict",
    "unresolved",
)


def _checks(snap: pr_activity.Snapshot) -> str:
    outcomes = {c.outcome for c in snap.checks}
    if not outcomes:
        return "none"

    if "pending" in outcomes:
        return "pending"

    return "failure" if "failed" in outcomes else "success"


def _known(found: object) -> str:
    return "unknown" if found is None else "known"


def facts(
    url: str, now: float, fetch: abc.Callable[[tuple[str, str]], pr_activity.Snapshot | None]
) -> list[live.Fact]:
    """`checks`, `draft`, `head`, `state` (OPEN, MERGED or CLOSED) and `mergeable`
    (MERGEABLE, CONFLICTING, or UNKNOWN while GitHub computes it) for a PR; `authored`,
    whether the user's account opened it; `assigned`, `approved` and `objecting`,
    space-separated logins of the people assigned to it, those who approved it, and those
    still requesting changes; `user_verdict`, the state of the user's account's latest
    review, "" for none; and `unresolved`, one line per unresolved review thread saying who
    spoke last in it: `user` or `other` (whether the user's account wrote it), the login,
    and the lemon name signing it, if any."""
    key = pr_url.parse(url)
    snap = fetch(key) if key else None
    if snap is None:
        return [live.fact("pr", url, field, "", now, "unavailable") for field in _FIELDS]

    return [
        live.fact("pr", url, "checks", _checks(snap), now),
        live.fact("pr", url, "draft", str(snap.draft).lower(), now),
        live.fact("pr", url, "head", snap.head, now),
        live.fact("pr", url, "state", snap.state, now),
        live.fact("pr", url, "mergeable", snap.mergeable, now),
        live.fact("pr", url, "authored", str(snap.authored).lower(), now),
        *(
            live.fact("pr", url, field, " ".join(people or ()), now, _known(people))
            for field, people in (
                ("assigned", snap.assigned),
                ("approved", snap.approved),
                ("objecting", snap.objecting),
            )
        ),
        live.fact(
            "pr", url, "user_verdict", snap.user_verdict or "", now, _known(snap.user_verdict)
        ),
        live.fact(
            "pr", url, "unresolved", "\n".join(snap.unresolved or ()), now, _known(snap.unresolved)
        ),
    ]
