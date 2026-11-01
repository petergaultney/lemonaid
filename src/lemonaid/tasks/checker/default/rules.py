"""The default checker: a starting policy, run as `python -m lemonaid.tasks.checker.default`.

It judges tasks here and working briefs with no task in `coverage`.

Lemonaid ships it so replay has a checker to run; a user's own package replaces it. It
reads only the line protocol.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from .. import checker_input, protocol
from . import coverage, holders, settings, waits

_REQUIRED = ("lifecycle", "holder", "revision", "assignment.assigned_at")


def _unstarted(
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


def _idle(task_id: str) -> str:
    return "\n".join(
        [
            "You are idle holding this task. Do one of these:",
            "- Act on it.",
            "- Hand it to the lemon that moves next:"
            f" `lemonaid task assign {task_id} --to BRIEF --reason TEXT`.",
            "- If a person who holds no task moves next, hand it to them and stay accountable:"
            f" `lemonaid task assign {task_id} --to human:NAME --accountable self --reason TEXT`.",
            "- If you are waiting for CI on the task's PR, give the task its PR and the inspector"
            f" waits while CI runs: `lemonaid task set-url {task_id} PR_URL --reason TEXT`.",
            "- If another lemon's task already covers this work, follow that one instead:"
            f" `lemonaid task observe OTHER_TASK_ID --instead-of {task_id}`.",
            "- If you are blocked on someone, set your brief's Status (such as `blocked`).",
        ]
    )


def _progress(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    if settings.fact(view, "lemon", brief, "activity") == "active":
        return [("recheck", view.subject, settings.at(policy, policy.now + policy.idle_grace))]

    if found := waits.findings(view, policy, brief):
        return found

    idle_since = max(
        checker_input.timestamp(settings.fact(view, "lemon", brief, "idle_since")),
        checker_input.timestamp(view.fields["assignment.attached_at"]),
    )  # the clock starts no earlier than the assignment, or the lemon's start with it
    if idle_since + policy.idle_grace > policy.now:
        return [("recheck", view.subject, settings.at(policy, idle_since + policy.idle_grace))]

    if found := waits.declared(view, policy, brief):
        return found

    return [
        (
            "challenge",
            view.subject,
            "progress",
            view.fields["revision"],
            "brief",
            brief,
            _idle(view.subject),
        )
    ]


def evaluate(view: checker_input.View) -> list[protocol.Record]:
    """The complete finding set for the input's task."""
    try:
        if missing := [f for f in _REQUIRED if not view.fields.get(f)]:
            raise settings.Unknown(f"missing task field {', '.join(missing)}")

        policy = settings.read(view.context)
        if view.fields["lifecycle"] == "closed":
            return [("ok", view.subject, "closed")]

        holder = view.fields["holder"]
        if not holder.startswith("brief:"):
            return holders.human_or_external(view, policy)

        brief = holder.removeprefix("brief:")
        found = (
            holders.unavailable(view, brief)
            or _unstarted(view, policy, brief)
            or _progress(view, policy, brief)
        )
    except (settings.Unknown, ValueError, KeyError) as e:
        return [("unknown", view.subject, str(e))]

    if any(r[0] in ("ok", "challenge", "adjudicate", "wait") for r in found):
        return found

    return [("ok", view.subject, "progressing"), *found]


def _watches(view: checker_input.View) -> list[tuple[str, str]]:
    if view.kind == "brief":
        return [("lemon", view.subject), ("brief", view.subject)]

    holder = view.fields.get("holder", "")
    return [
        ("task", view.subject),
        *(
            (kind, holder.removeprefix("brief:"))
            for kind in ("lemon", "brief")
            if holder.startswith("brief:")
        ),
        *([("pr", view.fields["subject_url"])] if view.fields.get("subject_url") else []),
        *(
            ("task", f.removeprefix("dependency."))
            for f in view.fields
            if f.startswith("dependency.")
        ),
    ]


def main(argv: abc.Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lemonaid.tasks.checker.default")
    parser.add_argument("operation", choices=("describe", "evaluate"))
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    view = checker_input.read(args.input.read_text())
    if args.operation == "describe":
        sys.stdout.write(protocol.render(("watch", *w) for w in _watches(view)))
        return

    found = coverage.evaluate(view) if view.kind == "brief" else evaluate(view)
    sys.stdout.write(protocol.render(found))
