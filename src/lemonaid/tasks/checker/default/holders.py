"""The default checker's rules for holders other than a working lemon: a human or external
party, and a brief whose lemon is gone."""

from .. import checker_input, protocol
from . import settings


def human_or_external(view: checker_input.View, policy: settings.Policy) -> list[protocol.Record]:
    task, holder = view.fields, view.fields["holder"]
    accountable = task.get("accountable_brief_id", "")
    recheck = task.get("recheck_at", "")
    if not accountable or (holder.startswith("external:") and not recheck):
        raise settings.Unknown(f"{holder} needs accountable_brief_id and, if external, recheck_at")

    if recheck and checker_input.timestamp(recheck) <= policy.now:
        return [
            (
                "challenge",
                view.subject,
                "recheck",
                recheck,
                "brief",
                accountable,
                f"re-check of {holder} is due",
            ),
        ]
    wait = "external-review" if holder.startswith("external:") else "human"
    until = checker_input.timestamp(recheck) if recheck else policy.now + policy.reconcile
    return [
        (
            "wait",
            view.subject,
            "next-move",
            wait,
            holder,
            settings.at(policy, until),
            f"{holder} holds it",
        )
    ]


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
