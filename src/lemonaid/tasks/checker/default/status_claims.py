"""The default checker's rule for a Status that its task's PR contradicts: `done` while the
PR is open; `merge` while it is a draft, its CI failed, it is already merged or closed, it
conflicts with its base, an unresolved review thread's last word is someone else's, or, on
the user's own PR, a person assigned to it hasn't approved it; `review` on the user's own
PR once a person has approved it and every assignee has; and `approve` once the user has
approved the PR.

A task in `check` was said to be done by its previous holder, so an open PR there is put to
the checking holder, who hands it back. An unknown PR fact never supports a challenge.
"""

from collections import abc

from .. import checker_input, protocol


def _known(view: checker_input.View, kind: str, key: str, field: str) -> str:
    found = view.facts.get((kind, key, field))
    return found.value if found is not None and found.availability == "known" else ""


def _people(view: checker_input.View, url: str, field: str) -> list[str] | None:
    found = view.facts.get(("pr", url, field))
    return found.value.split() if found is not None and found.availability == "known" else None


def _someone_elses(line: str, names: abc.Collection[str]) -> bool:
    """Whether an `unresolved` line's last word is signed by another lemon, or unsigned from
    another account. An unsigned comment from the user's account could be the holder's."""
    account, _, signer = [*line.split(" ", 2), "", ""][:3]
    return signer not in names if signer else account == "other"


def _unanswered(view: checker_input.View, url: str, brief: str) -> int:
    """Unresolved review threads on *url* whose last word is someone else's; 0 while the
    holder's names aren't known."""
    names = _known(view, "brief", brief, "signing_names").split()
    lines = _known(view, "pr", url, "unresolved").splitlines()
    return sum(1 for line in lines if names and _someone_elses(line, names))


def _merge(
    view: checker_input.View, task: str, url: str, state: str, brief: str
) -> tuple[str, str]:
    """What contradicts `merge`, as (evidence, reason); ("", "") for nothing."""
    if state in ("MERGED", "CLOSED"):
        return state, (
            f"its PR {url} is {state.lower()}. If the work is finished, close the task with"
            f" `lemonaid task close {task} --reason TEXT`, and change the Status."
        )

    if _known(view, "pr", url, "draft") == "true":
        return "draft", (
            f"its PR {url} is still a draft. Once review approves it, mark it ready with"
            f" `gh pr ready {url}`; until then the Status isn't `merge`."
        )

    if _known(view, "pr", url, "checks") == "failure":
        return "ci-failed", f"CI failed on its PR {url}. Clear `merge`, fix it and push."

    if _known(view, "pr", url, "mergeable") == "CONFLICTING":
        return "conflicting", (
            f"its PR {url} conflicts with its base. Clear `merge`, resolve the conflict and push."
        )

    if threads := _unanswered(view, url, brief):
        return f"unresolved={threads}", (
            f"{threads} review thread(s) on its PR {url} are unresolved, and the last word in"
            " each isn't yours. Answer each one, or resolve it if it's handled, before `merge`."
        )

    assigned, approved = _people(view, url, "assigned"), _people(view, url, "approved")
    if (
        _known(view, "pr", url, "authored") == "true"
        and assigned
        and approved is not None
        and (pending := [who for who in assigned if who not in approved])
    ):
        who = ", ".join(pending)
        return f"unapproved={who}", (
            f"{who} is assigned to its PR {url} and hasn't approved it. Set `review` until they"
            " approve."
        )

    return "", ""


def _review(view: checker_input.View, url: str, state: str) -> tuple[str, str]:
    """What contradicts `review` on the user's own PR, as (evidence, reason); ("", "") for
    nothing. A review of a teammate's PR isn't judged, and a person still requesting
    changes keeps review open."""
    assigned, approved = _people(view, url, "assigned"), _people(view, url, "approved")
    if (
        state != "OPEN"
        or _known(view, "pr", url, "authored") != "true"
        or assigned is None
        or _people(view, url, "objecting") != []
        or not approved
        or any(who not in approved for who in assigned)
    ):
        return "", ""

    who = ", ".join(approved)
    return f"approved={who}", (
        f"{who} approved its PR {url}, every assignee has approved, and nobody requests changes. If only your user's"
        " merge remains, set `merge`."
    )


def _approve(view: checker_input.View, url: str, state: str) -> tuple[str, str]:
    """What contradicts `approve`, as (evidence, reason); ("", "") for nothing."""
    if state != "OPEN" or _known(view, "pr", url, "user_verdict") != "APPROVED":
        return "", ""

    return "user-approved", (
        f"your user already approved its PR {url}. Clear the Status, or set the one that says"
        " who moves next."
    )


def _challenge(
    task: str, evidence: str, brief: str, reason: str, obligation: str = "status-claim"
) -> protocol.Record:
    """`status-claim` marks *brief*'s Status contested in the inbox; `check-claim` disputes
    another lemon's `done`, not *brief*'s own Status."""
    return ("challenge", task, obligation, evidence, "brief", brief, reason)


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
                "check-claim",
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

    evidence, reason = (
        _merge(view, task, url, state, brief)
        if claimed == "merge"
        else _review(view, url, state)
        if claimed == "review"
        else _approve(view, url, state)
        if claimed == "approve"
        else ("", "")
    )
    if not reason:
        return []

    return [
        _challenge(
            task,
            f"{url} {claimed} {evidence}",
            brief,
            f"Your brief's Status is `{claimed}`, but {reason}",
        )
    ]
