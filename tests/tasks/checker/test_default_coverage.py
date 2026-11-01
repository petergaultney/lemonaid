import pytest

from lemonaid.tasks.checker import checker_input, corpus, protocol
from lemonaid.tasks.checker.default import coverage, rules

from ..shared import NOW, fact


def _view(parent: str = "", *facts: dict[str, str]) -> checker_input.View:
    text = protocol.render(
        [
            ("context", "now", NOW),
            ("brief", "Loose.one", "parent", parent),
            *(("fact", *(f[name] for name in corpus.FACT_FIELDS)) for f in facts),
        ]
    )
    return checker_input.read(text)


def _working(since: str, activity: str = "idle", status: str = "") -> list[dict[str, str]]:
    return [
        fact("lemon", "Loose.one", "available", "true"),
        fact("lemon", "Loose.one", "activity", activity),
        fact("lemon", "Loose.one", "idle_since", since),
        fact("brief", "Loose.one", "status", status),
    ]


def test_a_brief_subject_watches_its_lemon_and_its_brief():
    assert rules._watches(_view()) == [("lemon", "Loose.one"), ("brief", "Loose.one")]


@pytest.mark.parametrize(
    ("parent", "told"),
    [("Lead.lead", "`lemonaid tell Lead.lead`"), ("", "lemonaid brief task ensure self")],
)
def test_an_idle_brief_past_its_grace_is_asked_for_a_task_through_its_parent(parent, told):
    [found] = coverage.evaluate(_view(parent, *_working("2026-10-31T11:00:00Z")))

    assert found[:3] == ("challenge", "Loose.one", "missing-task") and told in found[6]


@pytest.mark.parametrize(
    "facts",
    [
        _working("2026-10-31T11:55:00Z"),
        _working("2026-10-31T11:00:00Z", activity="active"),
        _working("2026-10-31T11:00:00Z", status="done"),
    ],
)
def test_a_recent_working_or_finished_brief_is_not_challenged(facts):
    assert coverage.evaluate(_view("", *facts))[0][0] == "ok"


def test_a_brief_with_unknown_idleness_is_unknown():
    assert coverage.evaluate(_view())[0][0] == "unknown"
