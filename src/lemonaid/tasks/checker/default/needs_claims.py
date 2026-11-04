"""The default checker's rule for a `blocked` or `alert` Status that its `Needs` doesn't
support: there is no `Needs`, or a `Needs` link names a file that doesn't exist or a
heading that file doesn't have.

It judges only what every way of asking shares; it never reads what a linked section says.
A file edited within `policy.file_quiet` may be mid-edit, so its headings aren't judged
yet, and an unknown fact never supports a challenge.
"""

import re

from .. import checker_input, protocol
from . import settings

_ASKING = frozenset({"blocked", "alert"})

_SEPARATORS = re.compile(r"[\W_]+")


def _known(view: checker_input.View, kind: str, key: str, field: str) -> str | None:
    found = view.facts.get((kind, key, field))
    return found.value if found is not None and found.availability == "known" else None


def _plain(heading: str) -> str:
    """A heading or anchor with case, punctuation and spacing dropped: `What's next?`,
    `whats-next` and `What's next` all name the same heading."""
    return _SEPARATORS.sub("", heading.casefold())


def _broken(view: checker_input.View, policy: settings.Policy, link: str) -> str:
    """Why *link* is broken, or "" when it isn't or that isn't known."""
    path, _, heading = link.partition("#")
    exists = _known(view, "file", path, "exists")
    if exists == "false":
        return f"{path} doesn't exist"

    modified = _known(view, "file", path, "modified_at")
    headings = _known(view, "file", path, "headings")
    if exists != "true" or not heading or modified is None or headings is None:
        return ""

    if checker_input.timestamp(modified) + policy.file_quiet > policy.now:
        return ""

    if _plain(heading) in {_plain(h) for h in headings.splitlines()}:
        return ""

    return f"{path} has no heading {heading!r}"


def _challenge(task: str, evidence: str, brief: str, reason: str) -> protocol.Record:
    return ("challenge", task, "status-claim", evidence, "brief", brief, reason)


def unsupported(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    """A challenge when *brief*'s `blocked` or `alert` has no `Needs`, or a broken `Needs`
    link; [] otherwise."""
    claimed = _known(view, "brief", brief, "status")
    if claimed not in _ASKING:
        return []

    needs = _known(view, "brief", brief, "needs")
    if needs == "":
        return [
            _challenge(
                view.subject,
                f"{claimed} no-needs",
                brief,
                f"Your brief's Status is `{claimed}`, but it has no `Needs` saying what your user"
                " must do. Add one, linking the section that asks it, or change the Status.",
            )
        ]

    links = _known(view, "brief", brief, "needs_links") or ""
    broken = [why for link in links.splitlines() if (why := _broken(view, policy, link))]
    if not broken:
        return []

    return [
        _challenge(
            view.subject,
            f"{claimed} broken-needs {'; '.join(broken)}",
            brief,
            f"Your brief's Status is `{claimed}`, but its `Needs` links somewhere that isn't"
            f" there: {'; '.join(broken)}. Fix the link so your user can find what you ask.",
        )
    ]
