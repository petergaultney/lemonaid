"""The default checker: a starting policy, run as `python -m lemonaid.tasks.checker.default`.

It judges tasks here and working briefs with no task in `coverage`.

Lemonaid ships it so replay has a checker to run; a user's own package replaces it. It
reads only the line protocol.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from .. import checker_input, protocol, stream
from . import closing, coverage, holders, settings, status_claims, waits

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
            "You are idle holding this task. Who moves next?",
            "- You: act on it.",
            "- Another lemon: hand it this task, since it must act on your result:"
            f" `lemonaid task assign {task_id} --to BRIEF --reason TEXT`. If that lemon holds a"
            " task of its own for what you wait on, wait for that one instead:"
            f" `lemonaid task depend {task_id} --on OTHER_TASK_ID`. A Status never waits on a"
            " lemon.",
            "- A person or a process: keep the task and set your brief's Status to say which:"
            " `blocked` for your user, `merge` when only your user's merge remains, `approve`"
            " for your user's approval, `review` for a teammate's review, `running` while a long"
            " process runs. A Status covers every task you hold.",
            "- CI on the task's PR: give the task its PR, and the inspector waits while CI runs:"
            f" `lemonaid task set-url {task_id} PR_URL --reason TEXT`.",
            "- Nobody, because the work is finished: close it, naming where the result is:"
            f" `lemonaid task close {task_id} --reason TEXT`.",
            "- Another lemon's task already covers this work: follow that one instead:"
            f" `lemonaid task observe OTHER_TASK_ID --instead-of {task_id}`.",
        ]
    )


def _progress(
    view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    if settings.fact(view, "lemon", brief, "activity") == "active":
        return [("recheck", view.subject, settings.at(policy, policy.now + policy.idle_grace))]

    contradicted = status_claims.contradicted(view, brief)
    if not contradicted and (found := waits.findings(view, policy, brief)):
        return found

    idle_since = max(
        checker_input.timestamp(settings.fact(view, "lemon", brief, "idle_since")),
        checker_input.timestamp(view.fields["assignment.attached_at"]),
    )  # the clock starts no earlier than the assignment, or the lemon's start with it
    if idle_since + policy.idle_grace > policy.now:
        return [("recheck", view.subject, settings.at(policy, idle_since + policy.idle_grace))]

    if contradicted:
        return contradicted  # no CI or dependency wait makes a contradicted Status true

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
            return closing.evaluate(view)

        holder = view.fields["holder"]
        if not holder.startswith("brief:"):
            raise settings.Unknown(f"{holder} isn't a lemon")

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
    if view.fields.get("lifecycle") == "closed":
        return [
            ("task", view.subject),
            *([("pr", view.fields["subject_url"])] if view.fields.get("subject_url") else []),
            *([("lineage", view.fields["closed.by"])] if view.fields.get("closed.by") else []),
        ]

    return [
        ("task", view.subject),
        *(
            (kind, holder.removeprefix("brief:"))
            for kind in ("lemon", "brief")
            if holder.startswith("brief:")
        ),
        *([("pr", view.fields["subject_url"])] if view.fields.get("subject_url") else []),
        *(
            ("lineage", who)
            for who in (view.fields.get("assignment.by", ""), view.fields.get("holder_parent", ""))
            if who
        ),
        *(
            ("task", f.removeprefix("dependency."))
            for f in view.fields
            if f.startswith("dependency.")
        ),
    ]


def respond(operation: str, text: str) -> str:
    """The output for one `describe` or `evaluate` input; raises ValueError for a malformed
    input or an unknown operation."""
    view = checker_input.read(text)
    if operation == "describe":
        return protocol.render(("watch", *w) for w in _watches(view))

    if operation != "evaluate":
        raise ValueError(f"unknown operation {operation!r}")

    return protocol.render(coverage.evaluate(view) if view.kind == "brief" else evaluate(view))


def main(argv: abc.Sequence[str] | None = None) -> None:
    """`describe` or `evaluate` one `--input` file, or `serve` requests on stdin."""
    parser = argparse.ArgumentParser(prog="lemonaid.tasks.checker.default")
    parser.add_argument("operation", choices=("describe", "evaluate", "serve"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    if args.operation == "serve":
        stream.serve(respond, sys.stdin, sys.stdout)
        return

    if args.input is None:
        parser.error(f"{args.operation} needs --input")

    sys.stdout.write(respond(args.operation, args.input.read_text()))
