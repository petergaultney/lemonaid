"""The default checker's waits: task dependencies, CI, and what happens once they release.

A released wait (CI finished, a dependency closed) is the holder's move only after the
release was delivered to it and the idle grace has passed since; until delivery the holder
is still waiting to hear. Dependency waits need the child's own latest finding, and a
dependency cycle is reported once, by the task with the smallest ID in it.
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
    return ("wait", s.view.task_id, "progress", kind, evidence, until, reason)


def _released(
    s: _Subject, fact_kind: str, fact_key: str, evidence: str, obligation: str, reason: str
) -> list[protocol.Record]:
    soon = settings.at(s.policy, s.policy.now + s.policy.reconcile)
    delivered = settings.fact(s.view, fact_kind, fact_key, "release_delivered_at")
    if not delivered:
        return [_wait(s, "release-notification", evidence, soon, f"{reason}; not yet delivered")]

    due = checker_input.timestamp(delivered) + s.policy.idle_grace
    if due > s.policy.now:
        return [("recheck", s.view.task_id, settings.at(s.policy, due))]

    return [("challenge", s.view.task_id, obligation, evidence, "brief", s.holder, reason)]


def _cycle(s: _Subject) -> list[protocol.Record]:
    members = settings.fact(s.view, "task", s.view.task_id, "cycle")
    if not members:
        return []

    loop = sorted(members.split(","))
    if s.view.task_id != loop[0]:
        return [("ok", s.view.task_id, f"cycle reported on {loop[0]}")]

    adjudicator = s.view.context.get("policy.adjudicator", "")
    if not adjudicator:
        raise settings.Unknown("dependency cycle with no policy.adjudicator")

    return [
        (
            "adjudicate",
            s.view.task_id,
            "dependency-cycle",
            f"cycle:{','.join(loop)}",
            "human",
            adjudicator,
            f"tasks {', '.join(loop)} wait on each other",
        ),
    ]


def _dependency(s: _Subject, child: str) -> list[protocol.Record]:
    if settings.fact(s.view, "task", child, "lifecycle") != "open":
        return _released(s, "task", child, f"task:{child}", "consume-result", f"{child} closed")

    finding = settings.fact(s.view, "task", child, "finding")
    if finding in _HEALTHY:
        until = settings.at(s.policy, s.policy.now + s.policy.reconcile)
        return [_wait(s, "waiting-for-task", f"task:{child}", until, f"waiting for {child}")]

    if finding in _UNHEALTHY:
        return [("ok", s.view.task_id, f"attention is on {child}, which has its own finding")]

    raise settings.Unknown(f"task {child} finding is {finding!r}")


def _ci(s: _Subject, url: str) -> list[protocol.Record]:
    checks = settings.fact(s.view, "pr", url, "checks")
    if checks == "none":
        return []

    head = settings.fact(s.view, "pr", url, "head")
    if checks == "pending":
        until = settings.at(s.policy, s.policy.now + s.policy.reconcile)
        return [_wait(s, "waiting-for-ci", f"{url}@{head}", until, "CI is running")]

    return _released(s, "pr", url, f"{url}@{head}:{checks}", "ci-result", f"CI {checks} on {head}")


def findings(
    view: checker_input.View, policy: settings.Policy, holder: str
) -> list[protocol.Record]:
    """Waits and release findings for the progress obligation; [] when none apply."""
    s = _Subject(view, policy, holder)
    dependencies = [f.removeprefix("dependency.") for f in view.task if f.startswith("dependency.")]
    if dependencies and (cycle := _cycle(s)):
        return cycle

    url = view.task.get("subject_url", "")
    found = [
        *(r for child in dependencies for r in _dependency(s, child)),
        *(_ci(s, url) if url else []),
    ]
    actionable = [r for r in found if r[0] != "ok"]
    if any(r[0] != "recheck" for r in actionable):
        return actionable

    return [r for r in found if r[0] == "ok"][:1] + actionable
