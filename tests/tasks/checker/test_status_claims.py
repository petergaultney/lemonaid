import pytest

from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import brief_says, fact, idle, snapshot, task

_PR = "https://github.com/o/r/pull/9"

_OPEN = {"state": "OPEN", "draft": "false", "checks": "success", "authored": "true"}


def _claim(status: str, signing_names: str = "Work Old", **pr: str) -> list[tuple[str, ...]]:
    facts = [
        *(f for f in idle() if f["kind"] == "lemon"),
        *brief_says(status=status),
        *([fact("brief", "Work.alpha", "signing_names", signing_names)] if signing_names else []),
        *(fact("pr", _PR, k, v) for k, v in pr.items()),
    ]
    [one] = corpus.inputs([corpus._snapshot(snapshot([task(subject_url=_PR)], facts), 0)])
    return rules.evaluate(checker_input.read(one.text))


def _challenged(records) -> bool:
    return any(r[0] == "challenge" and r[2] == "status-claim" for r in records)


@pytest.mark.parametrize(
    ("status", "pr", "said"),
    [
        ("merge", {**_OPEN, "mergeable": "CONFLICTING"}, "conflicts with its base"),
        ("merge", {**_OPEN, "unresolved": "other sam\nuser me Work"}, "1 review thread(s)"),
        ("merge", {**_OPEN, "unresolved": "user me Rev\nother sam Rev"}, "2 review thread(s)"),
        ("approve", {**_OPEN, "authored": "false", "user_verdict": "APPROVED"}, "already approved"),
    ],
)
def test_a_merge_or_approve_the_pr_contradicts_is_challenged(status, pr, said):
    [challenge] = _claim(status, **pr)

    assert challenge[2] == "status-claim" and challenge[5] == "Work.alpha"
    assert said in challenge[6]


@pytest.mark.parametrize(
    ("status", "pr", "signing_names"),
    [
        ("merge", {**_OPEN, "mergeable": "MERGEABLE", "unresolved": "user me Work"}, "Work Old"),
        ("merge", {**_OPEN, "unresolved": "user me Old\nuser me"}, "Work Old"),
        ("merge", {**_OPEN, "mergeable": "UNKNOWN", "unresolved": ""}, "Work Old"),
        ("merge", {**_OPEN, "unresolved": "other sam"}, ""),
        ("approve", {**_OPEN, "user_verdict": "COMMENTED"}, "Work Old"),
        ("approve", {**_OPEN, "user_verdict": ""}, "Work Old"),
        ("approve", {**_OPEN, "state": "MERGED", "user_verdict": "APPROVED"}, "Work Old"),
        ("review", {**_OPEN, "user_verdict": "APPROVED", "assigned": "sam"}, "Work Old"),
    ],
)
def test_a_status_the_pr_agrees_with_or_that_isnt_known_stands(status, pr, signing_names):
    assert not _challenged(_claim(status, signing_names, **pr))
