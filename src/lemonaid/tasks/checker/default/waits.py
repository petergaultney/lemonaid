"""The default checker's waits: task dependencies, CI, what the holder's brief declares,
and what happens once they release.

A closed dependency is the holder's move once the idle grace has passed since it closed.
CI known to be running on the task's PR is a wait; in any other state, or with no PR or no
CI known, an idle holder falls to the idle rule and its backoff. Dependency waits need the
child's own latest finding, and a dependency cycle is reported once, by the task with the
smallest ID in it.
"""

import typing as ty

from .. import checker_input, protocol
from . import settings

_HEALTHY = frozenset({"ok", "wait"})

_UNHEALTHY = frozenset({"challenge", "adjudicate"})


class _Subject(ty.NamedTuple):
    view: checker_input.View
    policy: settings.Policy
    holder: str


def _wait(s: _Subject, kind: str, evidence: str, until: str, reason: str) -> protocol.Record:
    return ("wait", s.view.subject, "progress", kind, evidence, until, reason)


def _released(s: _Subject, child: str) -> list[protocol.Record]:
    closed = settings.fact(s.view, "task", child, "released_at")
    due = checker_input.timestamp(closed) + s.policy.idle_grace
    if due > s.policy.now:
        return [("recheck", s.view.subject, settings.at(s.policy, due))]

    return [
        (
            "challenge",
            s.view.subject,
            "consume-result",
            f"task:{child}",
            "brief",
            s.holder,
            f"{child} closed",
        )
    ]


def _cycle(s: _Subject) -> list[protocol.Record]:
    members = settings.fact(s.view, "task", s.view.subject, "cycle")
    if not members:
        return []

    loop = sorted(members.split(","))
    if s.view.subject != loop[0]:
        return [("ok", s.view.subject, f"cycle reported on {loop[0]}")]

    adjudicator = s.view.context.get("policy.adjudicator", "")
    if not adjudicator:
        raise settings.Unknown("dependency cycle with no policy.adjudicator")

    return [
        (
            "adjudicate",
            s.view.subject,
            "dependency-cycle",
            f"cycle:{','.join(loop)}",
            "human",
            adjudicator,
            f"tasks {', '.join(loop)} wait on each other",
        ),
    ]


def _dependency(s: _Subject, child: str) -> list[protocol.Record]:
    if settings.fact(s.view, "task", child, "lifecycle") == "closed":
        return _released(s, child)

    finding = settings.fact(s.view, "task", child, "finding")
    if finding in _HEALTHY:
        until = settings.at(s.policy, s.policy.now + s.policy.reconcile)
        return [_wait(s, "waiting-for-task", f"task:{child}", until, f"waiting for {child}")]

    if finding in _UNHEALTHY:
        return [("ok", s.view.subject, f"attention is on {child}, which has its own finding")]

    raise settings.Unknown(f"task {child} finding is {finding!r}")


def _ci(s: _Subject, url: str) -> list[protocol.Record]:
    found = s.view.facts.get(("pr", url, "checks"))
    if found is None or found.availability != "known" or found.value != "pending":
        return []

    head = s.view.facts.get(("pr", url, "head"))
    until = settings.at(s.policy, s.policy.now + s.policy.reconcile)
    evidence = f"{url}@{head.value if head else ''}"
    return [_wait(s, "waiting-for-ci", evidence, until, "CI is running")]


def findings(
    view: checker_input.View, policy: settings.Policy, holder: str
) -> list[protocol.Record]:
    """Waits and release findings for the progress obligation; [] when none apply."""
    s = _Subject(view, policy, holder)
    dependencies = [
        f.removeprefix("dependency.") for f in view.fields if f.startswith("dependency.")
    ]
    if dependencies and (cycle := _cycle(s)):
        return cycle

    url = view.fields.get("subject_url", "")
    found = [
        *(r for child in dependencies for r in _dependency(s, child)),
        *(_ci(s, url) if url else []),
    ]
    actionable = [r for r in found if r[0] != "ok"]
    if any(r[0] != "recheck" for r in actionable):
        return actionable

    return [r for r in found if r[0] == "ok"][:1] + actionable


def declared(
    view: checker_input.View, policy: settings.Policy, holder: str
) -> list[protocol.Record]:
    """A wait, for every task the holder holds, when its brief has a Status other than
    `done`: every status says it waits on a person or a process."""
    state = settings.fact(view, "brief", holder, "status")
    if state in ("", "done"):
        return []

    until = settings.at(policy, policy.now + policy.reconcile)
    s = _Subject(view, policy, holder)
    return [_wait(s, "declared", f"brief:{holder}:{state}", until, f"its brief is {state}")]
