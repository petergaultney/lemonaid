import pytest

from lemonaid.tasks.checker import checker_input, corpus, replay
from lemonaid.tasks.checker.default import rules

from ..shared import fact, snapshot, task

_DOC = "/vault/decisions.md"


def _evaluate(held, facts, context=None):
    [one] = corpus.inputs([corpus._snapshot(snapshot([held], facts, context=context or {}), 0)])
    return rules.evaluate(checker_input.read(one.text))


def _rechecks(records):
    return [r for r in records if r[0] == "challenge" and r[2] == "status-recheck"]


def _blocked(turn="2026-10-31T11:50:00Z", modified="2026-10-31T11:40:00Z", status="blocked"):
    """A lemon `blocked` since 11:00 on a Needs bullet linking a doc edited at *modified*,
    whose last turn ended at *turn*."""
    return [
        fact("lemon", "Work.alpha", "activity", "idle"),
        fact("lemon", "Work.alpha", "idle_since", turn),
        fact("brief", "Work.alpha", "status", status),
        fact("brief", "Work.alpha", "needs", "decide"),
        fact("brief", "Work.alpha", "waiting_on", ""),
        fact("brief", "Work.alpha", "held", "t1"),
        fact("brief", "Work.alpha", "status_since", "2026-10-31T11:00:00Z"),
        fact("brief", "Work.alpha", "needs_since", "2026-10-31T11:05:00Z"),
        fact("brief", "Work.alpha", "needs_links", f"{_DOC}#Question"),
        fact("file", _DOC, "modified_at", modified),
        fact("file", _DOC, "sha256", "abc"),
    ]


def test_a_turn_after_an_edit_to_a_linked_file_that_left_the_status_alone_is_rechecked():
    [challenge] = _rechecks(_evaluate(task(), _blocked()))

    assert challenge[5] == "Work.alpha"
    assert _DOC in challenge[6] and "`blocked`" in challenge[6]
    assert f"{_DOC}@abc" in challenge[3]


@pytest.mark.parametrize(
    ("turn", "modified"),
    [
        ("2026-10-31T11:30:00Z", "2026-10-31T11:40:00Z"),  # no turn since the edit
        ("2026-10-31T11:50:00Z", "2026-10-31T11:02:00Z"),  # edited before the Needs changed
    ],
)
def test_no_recheck_without_an_edit_then_a_turn(turn, modified):
    assert _rechecks(_evaluate(task(), _blocked(turn, modified))) == []


@pytest.mark.parametrize("field", ["status_since", "needs_since"])
def test_a_missing_or_unknown_since_asks_nothing(field):
    missing = [f for f in _blocked() if f["field"] != field]
    unknown = [
        fact(f["kind"], f["key"], f["field"], "", "unknown") if f["field"] == field else f
        for f in _blocked()
    ]

    assert _rechecks(_evaluate(task(), missing)) == []
    assert _rechecks(_evaluate(task(), unknown)) == []


def test_an_unset_status_asks_nothing():
    assert _rechecks(_evaluate(task(), _blocked(status=""))) == []


def test_the_words_come_from_policy():
    found = _evaluate(task(), _blocked(), {"policy.recheck_text": "Use a decisions doc."})

    assert _rechecks(found)[0][6].endswith("Use a decisions doc.")


def test_a_request_no_turn_has_ended_since_is_put_to_a_lemon_holding_a_status():
    asked = task(**{"recheck.requested_at": "2026-10-31T11:55:00Z", "recheck.event": "9"})
    answered = task(**{"recheck.requested_at": "2026-10-31T11:45:00Z", "recheck.event": "9"})
    facts = [f for f in _blocked() if f["field"] != "needs_links"]
    no_status = [f for f in _blocked(status="") if f["field"] != "needs_links"]

    [challenge] = _rechecks(_evaluate(asked, facts))
    assert challenge[3] == "request 9" and "asked you to re-check" in challenge[6]
    assert _rechecks(_evaluate(answered, facts)) == []
    assert _rechecks(_evaluate(asked, no_status)) == []


def test_a_recheck_beside_a_dependencys_ok_is_a_valid_finding_set():
    held = task(
        **{
            "dependency.t2": "open",
            "recheck.requested_at": "2026-10-31T11:55:00Z",
            "recheck.event": "9",
        }
    )
    facts = [
        *(f for f in _blocked() if f["field"] != "needs_links"),
        fact("task", "t2", "lifecycle", "open"),
        fact("task", "t2", "finding", "challenge"),
        fact("task", "t1", "cycle", ""),
    ]

    found = _evaluate(held, facts)
    replay.check_findings("t1", found)

    assert [r[0] for r in found] == ["challenge"] and found[0][2] == "status-recheck"
