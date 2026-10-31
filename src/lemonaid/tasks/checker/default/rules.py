"""The default checker: a starting policy, run as `python -m lemonaid.tasks.checker.default`.

Lemonaid ships it so replay has a checker to run; a user's own package replaces it. It
reads only the line protocol.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from .. import checker_input, protocol
from . import settings, waits

_REQUIRED = ("lifecycle", "holder", "revision", "assignment.assigned_at")


def _human_or_external(view: checker_input.View, policy: settings.Policy) -> list[protocol.Record]:
    task, holder = view.task, view.task["holder"]
    accountable = task.get("accountable_brief_id", "")
    recheck = task.get("recheck_at", "")
    if not accountable or (holder.startswith("external:") and not recheck):
        raise settings.Unknown(f"{holder} needs accountable_brief_id and, if external, recheck_at")

    if recheck and checker_input.timestamp(recheck) <= policy.now:
        return [
            (
                "challenge",
                view.task_id,
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
            view.task_id,
            "next-move",
            wait,
            holder,
            settings.at(policy, until),
            f"{holder} holds it",
        )
    ]


def _acknowledgment(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    task = view.task
    if task.get("assignment.acknowledged_at"):
        return []

    transfer = task.get("assignment.transfer_event", task["revision"])
    if not task.get("assignment.attached_at"):
        if settings.fact(view, "lemon", brief, "attached") != "false":
            raise settings.Unknown("no attachment time, but the lemon is attached")

        due = checker_input.timestamp(task["assignment.assigned_at"]) + policy.unstarted_grace
        if due > policy.now:
            return [("recheck", view.task_id, settings.at(policy, due))]

        sponsor = task.get("sponsor", "")
        if not sponsor:
            raise settings.Unknown("unstarted assignment with no sponsor")

        return [
            (
                "challenge",
                view.task_id,
                "launch",
                transfer,
                "brief",
                sponsor,
                f"{brief} was assigned this task and has not started",
            )
        ]

    start = task.get("assignment.delivered_at")
    if not start and task.get("assignment.delivery") == "message":
        raise settings.Unknown("the assignment message hasn't been delivered yet")

    start = start or task["assignment.attached_at"]
    due = checker_input.timestamp(start) + policy.ack_grace
    if due > policy.now or settings.fact(view, "lemon", brief, "activity") == "active":
        return [
            (
                "recheck",
                view.task_id,
                settings.at(policy, max(due, policy.now + policy.idle_grace)),
            )
        ]

    return [
        (
            "challenge",
            view.task_id,
            "acknowledge",
            transfer,
            "brief",
            brief,
            f"run `lemonaid task acknowledge {view.task_id}` after reading the assignment",
        )
    ]


def _progress(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    if settings.fact(view, "lemon", brief, "activity") == "active":
        return [("recheck", view.task_id, settings.at(policy, policy.now + policy.idle_grace))]

    if found := waits.findings(view, policy, brief):
        return found

    idle_since = checker_input.timestamp(settings.fact(view, "lemon", brief, "idle_since"))
    if idle_since + policy.idle_grace > policy.now:
        return [("recheck", view.task_id, settings.at(policy, idle_since + policy.idle_grace))]

    return [
        (
            "challenge",
            view.task_id,
            "progress",
            view.task["revision"],
            "brief",
            brief,
            "idle with this task open and no recorded wait",
        )
    ]


def evaluate(view: checker_input.View) -> list[protocol.Record]:
    """The complete finding set for the input's task."""
    try:
        if missing := [f for f in _REQUIRED if not view.task.get(f)]:
            raise settings.Unknown(f"missing task field {', '.join(missing)}")

        policy = settings.read(view.context)
        if view.task["lifecycle"] == "closed":
            return [("ok", view.task_id, "closed")]

        holder = view.task["holder"]
        if not holder.startswith("brief:"):
            return _human_or_external(view, policy)

        brief = holder.removeprefix("brief:")
        found = _acknowledgment(view, policy, brief) or _progress(view, policy, brief)
    except (settings.Unknown, ValueError, KeyError) as e:
        return [("unknown", view.task_id, str(e))]

    if any(r[0] in ("ok", "challenge", "adjudicate", "wait") for r in found):
        return found

    return [("ok", view.task_id, "progressing"), *found]


def main(argv: abc.Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lemonaid.tasks.checker.default")
    parser.add_argument("operation", choices=("describe", "evaluate"))
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    view = checker_input.read(args.input.read_text())
    if args.operation == "describe":
        holder = view.task.get("holder", "")
        watches = [
            ("task", view.task_id),
            *([("lemon", holder.removeprefix("brief:"))] if holder.startswith("brief:") else []),
            *([("pr", view.task["subject_url"])] if view.task.get("subject_url") else []),
            *(
                ("task", f.removeprefix("dependency."))
                for f in view.task
                if f.startswith("dependency.")
            ),
        ]
        sys.stdout.write(protocol.render(("watch", *w) for w in watches))
        return

    sys.stdout.write(protocol.render(evaluate(view)))
