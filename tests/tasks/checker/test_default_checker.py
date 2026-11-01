import pytest

from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import brief_says, fact, idle, snapshot, task


def _evaluate(tasks, facts):
    [one] = corpus.inputs([corpus._snapshot(snapshot(tasks, facts), 0)])
    return rules.evaluate(checker_input.read(one.text))


def _kinds(records):
    return [(r[0], r[2]) if r[0] in ("challenge", "wait") else (r[0],) for r in records]


def _unstarted(assigned_at):
    return task(
        **{
            "assignment.assigned_at": assigned_at,
            "assignment.attached_at": "",
        }
    )


_NOT_STARTED = [fact("lemon", "Work.alpha", "attached", "false")]


def test_unstarted_child_gets_launch_grace():
    assert _kinds(_evaluate([_unstarted("2026-10-31T11:55:00Z")], _NOT_STARTED)) == [
        ("ok",),
        ("recheck",),
    ]


def test_a_missing_attachment_time_is_unknown_unless_the_lemon_is_known_not_started():
    assert _kinds(_evaluate([_unstarted("2026-10-31T11:00:00Z")], [])) == [("unknown",)]


def test_unstarted_child_past_launch_grace_challenges_only_its_sponsor():
    [finding] = _evaluate([_unstarted("2026-10-31T11:50:00Z")], _NOT_STARTED)

    assert finding[0] == "challenge"
    assert finding[2] == "launch"
    assert finding[5] == "Lead.lead"


def test_recently_idle_holder_is_rechecked_not_challenged():
    records = _evaluate([task()], idle(since="2026-10-31T11:59:00Z"))

    assert _kinds(records) == [("ok",), ("recheck",)]


@pytest.mark.parametrize("availability", ["unknown", "unavailable"])
def test_unknown_activity_is_never_an_accusation(availability):
    facts = [fact("lemon", "Work.alpha", "activity", "idle", availability)]

    assert _kinds(_evaluate([task()], facts)) == [("unknown",)]


def test_external_holder_needs_accountable_brief_and_recheck_date():
    external = task(holder="external:github", accountable_brief_id="Work.alpha")

    assert _kinds(_evaluate([external], [])) == [("unknown",)]
    assert _kinds(_evaluate([{**external, "recheck_at": "2026-11-01T00:00:00Z"}], [])) == [
        ("wait", "next-move")
    ]
    [due] = _evaluate([{**external, "recheck_at": "2026-10-31T09:00:00Z"}], [])
    assert (due[0], due[5]) == ("challenge", "Work.alpha")


def test_missing_required_field_is_unknown_and_closed_task_is_ok():
    assert _kinds(_evaluate([task(revision="")], [])) == [("unknown",)]
    assert _kinds(_evaluate([task(lifecycle="closed")], [])) == [("ok",)]


_URL = "https://example.com/pr/1"
_SOON = "2026-10-31T12:05:00Z"


def _ci(checks: str, since: str = "2026-10-31T11:50:00Z") -> list[dict[str, str]]:
    return [
        *idle(since=since),
        fact("pr", _URL, "checks", checks),
        fact("pr", _URL, "head", "abc"),
    ]


def test_wait_records_carry_type_before_evidence():
    external = task(
        holder="external:github",
        accountable_brief_id="Work.alpha",
        recheck_at="2026-11-01T00:00:00Z",
    )
    assert _evaluate([external], []) == [
        (
            "wait",
            "t1",
            "next-move",
            "external-review",
            "external:github",
            "2026-11-01T00:00:00Z",
            "external:github holds it",
        )
    ]


def test_running_ci_on_the_tasks_pr_is_a_wait_and_any_other_state_is_not():
    running = _evaluate([task(subject_url=_URL)], _ci("pending", "2026-10-31T11:30:00Z"))

    assert running[0][:5] == ("wait", "t1", "progress", "waiting-for-ci", f"{_URL}@abc")
    for checks in ("passed", "failed", "none"):
        overdue = _evaluate([task(subject_url=_URL)], _ci(checks, "2026-10-31T11:30:00Z"))

        assert _kinds(overdue) == [("challenge", "progress")]


def test_unknown_ci_falls_to_the_idle_rule():
    unknown = [*idle(since="2026-10-31T11:30:00Z"), fact("pr", _URL, "checks", "", "unknown")]

    assert _kinds(_evaluate([task(subject_url=_URL)], unknown)) == [("challenge", "progress")]


def _child(lifecycle: str, finding: str = "", closed: str = "") -> list[dict[str, str]]:
    return [
        *idle(),
        fact("task", "t1", "cycle", ""),
        fact("task", "t2", "lifecycle", lifecycle),
        *([fact("task", "t2", "finding", finding)] if finding else []),
        *([fact("task", "t2", "released_at", closed)] if closed else []),
    ]


def test_a_dependency_justifies_a_wait_only_while_it_is_healthy():
    held = task(**{"dependency.t2": "pending"})

    assert _evaluate([held], _child("open", "wait"))[0][:5] == (
        "wait",
        "t1",
        "progress",
        "waiting-for-task",
        "task:t2",
    )
    assert _kinds(_evaluate([held], _child("open", "challenge"))) == [("ok",)]
    assert _kinds(_evaluate([held], _child("open"))) == [("unknown",)]


def test_a_closed_dependency_is_the_holders_move_once_the_grace_since_it_closed_passes():
    held = task(**{"dependency.t2": "pending"})

    assert _kinds(_evaluate([held], _child("closed", closed="2026-10-31T11:59:30Z"))) == [
        ("ok",),
        ("recheck",),
    ]
    assert _evaluate([held], _child("closed", closed="2026-10-31T11:00:00Z")) == [
        ("challenge", "t1", "consume-result", "task:t2", "brief", "Work.alpha", "t2 closed"),
    ]


def test_a_cycle_is_reported_once_by_its_smallest_task():
    cycle = [*idle(), fact("task", "t1", "cycle", "t2,t1"), fact("task", "t2", "cycle", "t1,t2")]
    first = task(**{"dependency.t2": "pending"})
    second = task(task_id="t2", **{"dependency.t1": "pending"})

    with_adjudicator = corpus._snapshot(
        snapshot([first, second], cycle, context={"policy.adjudicator": "sam"}), 0
    )
    found = [
        rules.evaluate(checker_input.read(one.text)) for one in corpus.inputs([with_adjudicator])
    ]

    assert found[0][0][:6] == (
        "adjudicate",
        "t1",
        "dependency-cycle",
        "cycle:t1,t2",
        "human",
        "sam",
    )
    assert _kinds(found[1]) == [("ok",)]


@pytest.mark.parametrize(
    "said",
    [
        {"status": "blocked", "needs": "Design acceptance"},
        {"status": "review", "waiting_on": "- The reviewer's verdict"},
    ],
)
def test_an_idle_holder_whose_brief_status_declares_a_wait_is_not_challenged(said):
    lemon = [f for f in idle() if f["kind"] == "lemon"]

    assert _kinds(_evaluate([task()], [*lemon, *brief_says(**said)])) == [("wait", "progress")]


@pytest.mark.parametrize("said", [{}, {"waiting_on": "- CI on the PR"}, {"needs": "A ruling"}])
def test_an_idle_holder_is_challenged_unless_its_status_declares_a_wait(said):
    lemon = [f for f in idle() if f["kind"] == "lemon"]

    assert _kinds(_evaluate([task()], [*lemon, *brief_says(**said)])) == [("challenge", "progress")]


@pytest.mark.parametrize(
    ("waiting_on", "expected"),
    [
        ("- A reviewer for t1", [("wait", "progress")]),
        ("- A reviewer for t2", [("challenge", "progress")]),
        ("- A reviewer", [("unknown",)]),
    ],
)
def test_a_declared_wait_covers_only_the_task_it_names_when_the_brief_holds_several(
    waiting_on, expected
):
    lemon = [f for f in idle() if f["kind"] == "lemon"]
    said = brief_says(status="review", waiting_on=waiting_on, held="t1 t2")

    assert _kinds(_evaluate([task()], [*lemon, *said])) == expected


@pytest.mark.parametrize(
    ("started", "expected"),
    [
        ("2026-10-31T11:59:30Z", [("ok",), ("recheck",)]),
        ("2026-10-31T11:40:00Z", [("challenge", "progress")]),
    ],
)
def test_the_idle_clock_starts_no_earlier_than_the_assignment(started, expected):
    records = _evaluate(
        [task(**{"assignment.attached_at": started})], idle(since="2026-10-31T11:00:00Z")
    )

    assert _kinds(records) == expected


def test_the_idle_challenge_lists_each_honest_way_out():
    [challenge] = _evaluate([task()], idle(since="2026-10-31T11:00:00Z"))

    for command in (
        "task assign t1 --to BRIEF",
        "--to human:NAME --accountable self",
        "--instead-of t1",
        "task set-url t1",
    ):
        assert command in challenge[6]


def test_a_gone_holders_task_goes_to_its_parent_when_no_one_handed_it_over():
    orphan = task(previous_holder="", sponsor="", holder_parent="Lead.lead")
    gone = [fact("lemon", "Work.alpha", "available", "false")]

    [found] = _evaluate([orphan], gone)

    assert found[:3] == ("challenge", "t1", "holder-unavailable") and found[5] == "Lead.lead"
