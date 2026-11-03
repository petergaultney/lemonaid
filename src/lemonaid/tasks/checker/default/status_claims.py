"""The default checker's rule for a Status that its task's PR contradicts: `done` while the
PR is open, or `merge` while it is a draft, its CI failed, or it is already merged or closed.

A task in `check` was said to be done by its previous holder, so an open PR there is put to
the checking holder, who hands it back. An unknown PR fact never supports a challenge.
"""

from .. import checker_input, protocol


def _known(view: checker_input.View, kind: str, key: str, field: str) -> str:
    found = view.facts.get((kind, key, field))
    return found.value if found is not None and found.availability == "known" else ""


def _merge(task: str, url: str, state: str, draft: str, checks: str) -> str:
    if state in ("MERGED", "CLOSED"):
        return (
            f"its PR {url} is {state.lower()}. If the work is finished, close the task with"
            f" `lemonaid task close {task} --reason TEXT`, and change the Status."
        )

    if draft == "true":
        return (
            f"its PR {url} is still a draft. Once review approves it, mark it ready with"
            f" `gh pr ready {url}`; until then the Status isn't `merge`."
        )

    if checks == "failure":
        return f"CI failed on its PR {url}. Clear `merge`, fix it and push."

    return ""


def _challenge(task: str, evidence: str, brief: str, reason: str) -> protocol.Record:
    return ("challenge", task, "status-claim", evidence, "brief", brief, reason)


def contradicted(view: checker_input.View, brief: str) -> list[protocol.Record]:
    """A challenge when the PR of the task *brief* holds contradicts what its Status or its
    `done` claims; [] otherwise."""
    url, task = view.fields.get("subject_url", ""), view.subject
    state = _known(view, "pr", url, "state") if url else ""
    if view.fields.get("lifecycle") == "check":
        said = view.fields.get("previous_holder", "").removeprefix("brief:")
        if state != "OPEN" or not said:
            return []

        return [
            _challenge(
                task,
                f"{url} OPEN",
                brief,
                f"{said} said this task is done, but its PR {url} is still open, and nobody"
                f" is done until their PR merges. Hand it back with `lemonaid task assign {task}"
                f" --to {said} --reason TEXT`. If the work was dropped, close the PR and then the task.",
            )
        ]

    claimed = _known(view, "brief", brief, "status") if state else ""
    if claimed == "done" and state == "OPEN":
        return [
            _challenge(
                task,
                f"{url} OPEN done",
                brief,
                f"Your brief's Status is `done`, but this task's PR {url} is still open, and you"
                " aren't done until it merges. Set the Status that says who moves next.",
            )
        ]

    if claimed != "merge":
        return []

    draft, checks = _known(view, "pr", url, "draft"), _known(view, "pr", url, "checks")
    if reason := _merge(task, url, state, draft, checks):
        return [
            _challenge(
                task,
                f"{url} {state} draft={draft} checks={checks} merge",
                brief,
                f"Your brief's Status is `merge`, but {reason}",
            )
        ]

    return []
