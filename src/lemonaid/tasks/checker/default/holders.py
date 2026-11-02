"""The default checker's rule for a holder whose lemon is gone."""

from .. import checker_input, protocol
from . import settings


def unavailable(view: checker_input.View, brief: str) -> list[protocol.Record]:
    """A challenge to whoever handed the task over, or else its sponsor or the holder's
    parent, when its holder's lemon is gone; a task is never left with nobody to move."""
    available = view.facts.get(("lemon", brief, "available"))
    if available is None or available.availability != "known" or available.value != "false":
        return []

    fallback = next(
        (
            who
            for who in (
                view.fields.get("previous_holder", "").removeprefix("brief:"),
                view.fields.get("sponsor", ""),
                view.fields.get("holder_parent", ""),
            )
            if who and who != brief and ":" not in who
        ),
        "",
    )
    if not fallback:
        raise settings.Unknown(f"{brief} is gone and has no one to hand its task to")

    return [
        (
            "challenge",
            view.subject,
            "holder-unavailable",
            view.fields.get("assignment.transfer_event", view.fields["revision"]),
            "brief",
            fallback,
            f"{brief} holds this task but its lemon is gone; take it back or reassign it",
        )
    ]
