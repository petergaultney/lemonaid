"""The default checker's re-checks of a Status: after a file its brief's Needs links to
changed and the lemon took a turn without changing its Status or Needs, and after someone
ran `lemonaid task recheck`. Only a lemon idle with a Status is asked.

The words come from `policy.recheck_text`, after a sentence saying what prompted the
re-check, so a user's conventions ride in their config rather than in this rule. Each
prompt is its own evidence, so it is sent once.
"""

import datetime

from .. import checker_input, protocol
from . import settings

OBLIGATION = "status-recheck"

_TEXT = (
    "Re-read what your Status and Needs say you wait on. If it has been answered or done, act"
    " on it and change them; if they still hold, leave them."
)


def _known(view: checker_input.View, kind: str, key: str, field: str) -> str:
    found = view.facts.get((kind, key, field))
    return found.value if found is not None and found.availability == "known" else ""


def _ask(view: checker_input.View, brief: str, evidence: str, why: str) -> protocol.Record:
    text = view.context.get("policy.recheck_text", "") or _TEXT
    return ("challenge", view.subject, OBLIGATION, evidence, "brief", brief, f"{why} {text}")


def _requested(
    view: checker_input.View, brief: str, status: str, turn: datetime.datetime
) -> list[protocol.Record]:
    """A request no turn has ended since."""
    at = view.fields.get("recheck.requested_at", "")
    if not at or turn >= checker_input.timestamp(at):
        return []

    return [
        _ask(
            view,
            brief,
            f"request {view.fields.get('recheck.event', at)}",
            f"Someone asked you to re-check your Status `{status}`.",
        )
    ]


def _claimed_at(view: checker_input.View, brief: str) -> datetime.datetime | None:
    """When the brief's Status or its Needs last changed, whichever was later; None unless
    both times are known."""
    status_since = _known(view, "brief", brief, "status_since")
    needs_since = _known(view, "brief", brief, "needs_since")
    if not status_since or not needs_since:
        return None

    return max(checker_input.timestamp(status_since), checker_input.timestamp(needs_since))


def _edited(
    view: checker_input.View, brief: str, status: str, turn: datetime.datetime
) -> list[protocol.Record]:
    """Linked files changed after the Status and Needs were set, and before a turn that left
    both as they were."""
    claimed = _claimed_at(view, brief)
    if claimed is None:
        return []

    changed = []
    for link in _known(view, "brief", brief, "needs_links").splitlines():
        path = link.partition("#")[0]
        modified = _known(view, "file", path, "modified_at")
        if path and modified and claimed < checker_input.timestamp(modified) < turn:
            changed.append((path, _known(view, "file", path, "sha256") or modified))
    if not changed:
        return []

    paths = sorted(dict(changed))
    return [
        _ask(
            view,
            brief,
            " ".join([checker_input.rfc3339(claimed), *(f"{p}@{h}" for p, h in sorted(changed))]),
            f"{', '.join(paths)} changed after you set your Status `{status}` and its Needs, and"
            " your last turn left both as they were.",
        )
    ]


def findings(
    view: checker_input.View, _policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    """Re-check challenges for the idle *brief* holding the input's task; [] when it has no
    Status or any fact needed is unknown."""
    status = _known(view, "brief", brief, "status")
    idle_since = _known(view, "lemon", brief, "idle_since")
    if not status or not idle_since or _known(view, "lemon", brief, "activity") != "idle":
        return []

    turn = checker_input.timestamp(idle_since)
    return [*_requested(view, brief, status, turn), *_edited(view, brief, status, turn)]
