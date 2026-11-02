"""The default checker's rule for a closed task: one whose subject is a GitHub PR should
not close while that PR is still open.

A lemon closes its own tasks, so this is the check on its word. A task closed by a person,
about anything but a PR, once its PR merged or was closed, or while another open task
carries that PR (a review task closed beside the PR's own), is taken as finished.
"""

import re

from .. import checker_input, protocol
from . import holders, settings

_PR = re.compile(r"https://github\.com/[^/]+/[^/]+/pull/\d+/?$")


def _told(view: checker_input.View, closer: str) -> str:
    """The closer if it is live, else the nearest live lemon above it."""
    chain = settings.fact(view, "lineage", closer, "chain").split()
    told = next((who for who in chain if holders.live(view, who) == "true"), "")
    if not told:
        raise settings.Unknown(f"{closer} isn't live, and no lemon above it is")

    return told


def evaluate(view: checker_input.View) -> list[protocol.Record]:
    url = view.fields.get("subject_url", "")
    closer = view.fields.get("closed.by", "")
    if not _PR.match(url) or closer in ("", "cli"):
        return [("ok", view.subject, "closed")]

    if carriers := view.fields.get("closed.carried_by", ""):
        return [("ok", view.subject, f"closed, its PR carried by {carriers}")]

    state = settings.fact(view, "pr", url, "state")
    if state != "OPEN":
        return [("ok", view.subject, f"closed, its PR {state.lower()}")]

    task = view.subject
    return [
        (
            "challenge",
            task,
            "closed-unmerged",
            f"{url} {state}",
            "brief",
            _told(view, closer),
            f"{closer} closed this task, but its PR {url} is still open and no open task"
            f" carries it. If the work isn't finished, reopen it with `lemonaid task reopen"
            f" {task} --reason TEXT`. If another PR carried it, point the task there with"
            f" `lemonaid task set-url {task} PR_URL --reason TEXT`. If the work was dropped,"
            " close the PR. This is sent once.",
        )
    ]
