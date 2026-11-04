from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import brief_says, fact, snapshot, task


def _view(status: str) -> checker_input.View:
    facts = [
        fact("lemon", "Work.alpha", "activity", "idle"),
        fact("lemon", "Work.alpha", "idle_since", "2026-10-31T11:00:00Z"),
        *brief_says(status=status, needs="your user picks a name"),
    ]
    [one] = corpus.inputs([corpus._snapshot(snapshot([task()], facts), 0)])
    return checker_input.read(one.text)


def _stale_blocked(view, policy, brief):
    if view.facts[("brief", brief, "status")].value != "blocked":
        return []

    return [("challenge", view.subject, "status-claim", "stale", "brief", brief, "re-check")]


def test_a_claim_rule_added_to_the_default_runs_before_a_declared_wait_excuses_the_holder():
    mine = rules.DEFAULT._replace(claims=(_stale_blocked, *rules.DEFAULT.claims))

    assert rules.evaluate(_view("blocked"))[0][0] == "wait"
    assert rules.evaluate(_view("blocked"), mine)[0][6] == "re-check"
    assert rules.evaluate(_view("running"), mine)[0][0] == "wait"


def test_a_stage_with_no_rule_that_speaks_falls_through_to_the_next():
    quiet = rules.DEFAULT._replace(declared=(), idle=())

    assert rules.evaluate(_view("blocked"), quiet) == [("ok", "t1", "progressing")]
