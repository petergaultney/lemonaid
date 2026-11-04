import pytest

from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import brief_says, fact, idle, snapshot, task

_PR = "https://github.com/o/r/pull/9"

_OPEN = {"state": "OPEN", "draft": "false", "checks": "success", "authored": "true"}


def _claim(status: str, signing_name: str = "Work", **pr: str) -> list[tuple[str, ...]]:
    facts = [
        *(f for f in idle() if f["kind"] == "lemon"),
        *brief_says(status=status),
        *([fact("brief", "Work.alpha", "signing_name", signing_name)] if signing_name else []),
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
        ("merge", {**_OPEN, "unresolved": "@sam Work"}, "1 review thread(s)"),
        ("merge", {**_OPEN, "unresolved": "Rev Rev"}, "2 review thread(s)"),
        ("approve", {**_OPEN, "authored": "false", "user_verdict": "APPROVED"}, "already approved"),
    ],
)
def test_a_merge_or_approve_the_pr_contradicts_is_challenged(status, pr, said):
    [challenge] = _claim(status, **pr)

    assert challenge[2] == "status-claim" and challenge[5] == "Work.alpha"
    assert said in challenge[6]


@pytest.mark.parametrize(
    ("status", "pr", "signing_name"),
    [
        ("merge", {**_OPEN, "mergeable": "MERGEABLE", "unresolved": "Work"}, "Work"),
        ("merge", {**_OPEN, "mergeable": "UNKNOWN", "unresolved": ""}, "Work"),
        ("merge", {**_OPEN, "unresolved": "@sam"}, ""),
        ("approve", {**_OPEN, "user_verdict": "COMMENTED"}, "Work"),
        ("approve", {**_OPEN, "user_verdict": ""}, "Work"),
        ("approve", {**_OPEN, "state": "MERGED", "user_verdict": "APPROVED"}, "Work"),
        ("review", {**_OPEN, "user_verdict": "APPROVED", "assigned": "sam"}, "Work"),
    ],
)
def test_a_status_the_pr_agrees_with_or_that_isnt_known_stands(status, pr, signing_name):
    assert not _challenged(_claim(status, signing_name, **pr))
