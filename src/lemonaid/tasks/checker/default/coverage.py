"""The default checker's rule for a working brief that lemonaid found with no task: once
it has idled past the coverage grace, ask it to get one, through its parent if it has one.
"""

from .. import checker_input, protocol
from . import settings

_ENSURE = (
    "run `lemonaid brief task ensure self` with --task TASK_ID, --task TASK_ID --observe,"
    " --no-task REASON, or no option for a new task"
)


def _ask(parent: str) -> str:
    if not parent:
        return f"your brief has no task, exemption or observed task: {_ENSURE}"

    return (
        f"your brief has no task: ask your parent with `lemonaid tell {parent}` to define it"
        f" (it should ask the human for a ruling if it isn't sure), then {_ENSURE}"
    )


def evaluate(view: checker_input.View) -> list[protocol.Record]:
    brief = view.subject
    try:
        policy = settings.read(view.context)
        if (
            settings.fact(view, "lemon", brief, "available") == "false"
            or settings.fact(view, "brief", brief, "status") == "done"
        ):
            return [("ok", brief, "not working")]

        if settings.fact(view, "lemon", brief, "activity") == "active":
            return [("ok", brief, "working")]

        since = checker_input.timestamp(settings.fact(view, "lemon", brief, "idle_since"))
        if since + policy.coverage_grace > policy.now:
            return [
                ("ok", brief, "recently active"),
                ("recheck", brief, settings.at(policy, since + policy.coverage_grace)),
            ]
    except (settings.Unknown, ValueError, KeyError) as e:
        return [("unknown", brief, str(e))]

    return [
        (
            "challenge",
            brief,
            "missing-task",
            "",
            "brief",
            brief,
            _ask(view.fields.get("parent", "")),
        )
    ]
