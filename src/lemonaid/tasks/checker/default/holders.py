"""The default checker's rule for a holder whose lemon is gone."""

from .. import checker_input, protocol
from . import settings


def live(view: checker_input.View, lemon: str) -> str:
    found = view.facts.get(("lemon", lemon, "live"))
    return found.value if found is not None and found.availability == "known" else ""


def unavailable(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    """A challenge, once the holder has started with its task and its lemon is no longer
    live, to whoever assigned the task, or failing that to the nearest live lemon above
    them, and then above the holder; a task is never left with nobody to move."""
    if live(view, brief) != "false" or not view.fields.get("assignment.attached_at"):
        return []

    told = next(
        (
            who
            for start in (view.fields.get("assignment.by"), view.fields.get("holder_parent"))
            if start
            for who in settings.fact(view, "lineage", start, "chain").split()
            if who != brief and live(view, who) == "true"
        ),
        "",
    )
    if not told:
        raise settings.Unknown(f"{brief} isn't live, and no lemon above it is")

    task = view.subject
    return [
        (
            "challenge",
            view.subject,
            "holder-unavailable",
            view.fields.get("assignment.transfer_event", view.fields["revision"]),
            "brief",
            told,
            f"{brief} holds this task, but its lemon isn't live. Resume it with"
            f" `lemonaid lemon resume {brief}`, or hand the task to a live lemon with"
            f" `lemonaid task assign {task} --to BRIEF --reason TEXT`.",
        )
    ]
