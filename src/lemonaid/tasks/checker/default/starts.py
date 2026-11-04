"""The default checker's rule for an assignment whose lemon never started."""

from .. import checker_input, protocol
from . import settings


def unstarted(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    """An assignment whose brief's lemon never started is its sponsor's to chase; []
    once the lemon has started."""
    task = view.fields
    if task.get("assignment.attached_at"):
        return []

    if settings.fact(view, "lemon", brief, "attached") != "false":
        raise settings.Unknown("no attachment time, but the lemon is attached")

    due = checker_input.timestamp(task["assignment.assigned_at"]) + policy.unstarted_grace
    if due > policy.now:
        return [("recheck", view.subject, settings.at(policy, due))]

    sponsor = task.get("sponsor", "")
    if not sponsor:
        raise settings.Unknown("unstarted assignment with no sponsor")

    return [
        (
            "challenge",
            view.subject,
            "launch",
            task.get("assignment.transfer_event", task["revision"]),
            "brief",
            sponsor,
            f"{brief} was assigned this task and has not started",
        )
    ]
