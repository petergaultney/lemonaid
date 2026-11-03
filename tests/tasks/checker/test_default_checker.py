import pytest

from lemonaid.tasks.checker import checker_input, corpus, protocol
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


def test_a_holder_that_isnt_a_lemon_is_unknown():
    assert _kinds(_evaluate([task(holder="human:ben")], [])) == [("unknown",)]


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


def test_a_declared_status_covers_every_task_the_brief_holds():
    lemon = [f for f in idle() if f["kind"] == "lemon"]
    said = brief_says(status="merge", held="t1 t2")

    assert _kinds(_evaluate([task()], [*lemon, *said])) == [("wait", "progress")]


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
        "set your brief's Status",
        "--instead-of t1",
        "task set-url t1",
    ):
        assert command in challenge[6]


def _lineage(start: str, *chain: tuple[str, str]) -> list[dict[str, str]]:
    return [
        fact("lineage", start, "chain", " ".join(who for who, _ in chain)),
        *(fact("lemon", who, "live", alive) for who, alive in chain),
    ]


def test_a_dead_holder_is_reported_to_its_assigner_while_live():
    gone = [
        fact("lemon", "Work.alpha", "live", "false"),
        *_lineage("Review.one", ("Review.one", "true"), ("Lead.lead", "true")),
    ]

    [found] = _evaluate([task(**{"assignment.by": "Review.one"})], gone)

    assert found[:3] == ("challenge", "t1", "holder-unavailable") and found[5] == "Review.one"
    assert "lemonaid lemon resume Work.alpha" in found[6]


def test_a_dead_assigner_passes_the_report_up_its_lineage_then_the_holders():
    assigned = task(**{"assignment.by": "Review.one"}, holder_parent="Lead.two")
    gone = [
        fact("lemon", "Work.alpha", "live", "false"),
        *_lineage("Review.one", ("Review.one", "false"), ("Lead.lead", "false")),
        *_lineage("Lead.two", ("Lead.two", "false"), ("Top.hq", "true")),
    ]

    [found] = _evaluate([assigned], gone)

    assert found[5] == "Top.hq"


def test_a_dead_holder_with_no_live_lemon_above_is_unknown_and_an_unstarted_one_isnt_judged_dead():
    gone = [
        fact("lemon", "Work.alpha", "live", "false"),
        *_lineage("Review.one", ("Review.one", "false")),
    ]

    assert _kinds(_evaluate([task(**{"assignment.by": "Review.one"})], gone)) == [("unknown",)]
    unstarted = task(**{"assignment.by": "Review.one", "assignment.attached_at": ""})
    assert ("holder-unavailable",) not in [k[1:] for k in _kinds(_evaluate([unstarted], gone))]


_PR = "https://github.com/acme/widgets/pull/7"


def _closed(by: str = "Work.alpha", url: str = _PR) -> dict[str, str]:
    return task(lifecycle="closed", subject_url=url, **{"closed.by": by})


def test_a_task_closed_on_an_open_pr_is_put_to_its_closer_or_the_nearest_live_lemon_above():
    live = [fact("pr", _PR, "state", "OPEN"), *_lineage("Work.alpha", ("Work.alpha", "true"))]
    dead = [
        fact("pr", _PR, "state", "OPEN"),
        *_lineage("Work.alpha", ("Work.alpha", "false"), ("Lead.lead", "true")),
    ]

    [told] = _evaluate([_closed()], live)
    [passed_up] = _evaluate([_closed()], dead)

    assert told[:3] == ("challenge", "t1", "closed-unmerged") and told[5] == "Work.alpha"
    assert "lemonaid task reopen t1" in told[6] and "is still open" in told[6]
    assert passed_up[5] == "Lead.lead"


def test_a_closing_is_accepted_once_the_pr_merged_or_closed_by_a_person_or_without_a_pr():
    merged = [fact("pr", _PR, "state", "MERGED")]
    abandoned = [fact("pr", _PR, "state", "CLOSED")]

    assert _kinds(_evaluate([_closed()], merged)) == [("ok",)]
    assert _kinds(_evaluate([_closed()], abandoned)) == [("ok",)]
    assert _kinds(_evaluate([_closed(by="cli")], [])) == [("ok",)]
    assert _kinds(_evaluate([_closed(url="https://example.com/doc")], [])) == [("ok",)]
    assert _kinds(_evaluate([_closed()], [])) == [("unknown",)]


def test_a_task_closed_while_another_open_task_carries_its_pr_is_accepted():
    review = {**_closed(), "closed.carried_by": "t2"}

    assert _kinds(_evaluate([review], [fact("pr", _PR, "state", "OPEN")])) == [("ok",)]


def _claim(status: str, lifecycle: str = "open", **pr: str) -> list[protocol.Record]:
    lemon = [f for f in idle() if f["kind"] == "lemon"]
    facts = [*lemon, *brief_says(status=status), *(fact("pr", _PR, k, v) for k, v in pr.items())]
    held = task(subject_url=_PR, lifecycle=lifecycle, previous_holder="brief:Work.beta")
    return _evaluate([held], facts)


@pytest.mark.parametrize(
    ("status", "pr", "said"),
    [
        ("done", {"state": "OPEN"}, "aren't done until it merges"),
        ("merge", {"state": "OPEN", "draft": "true"}, f"gh pr ready {_PR}"),
        ("merge", {"state": "OPEN", "draft": "false", "checks": "failure"}, "CI failed"),
        ("merge", {"state": "MERGED"}, "lemonaid task close t1"),
    ],
)
def test_a_status_its_tasks_pr_contradicts_is_put_to_the_holder(status, pr, said):
    [challenge] = _claim(status, **pr)

    assert challenge[:3] == ("challenge", "t1", "status-claim") and challenge[5] == "Work.alpha"
    assert said in challenge[6]


@pytest.mark.parametrize(
    ("status", "pr"),
    [
        ("done", {"state": "MERGED"}),
        ("merge", {"state": "OPEN", "draft": "false", "checks": "success"}),
        ("merge", {}),
    ],
)
def test_a_status_its_tasks_pr_agrees_with_or_that_nothing_is_known_about_stands(status, pr):
    assert ("challenge", "status-claim") not in _kinds(_claim(status, **pr))


def test_a_task_in_check_on_an_open_pr_is_put_to_its_checker_to_hand_back():
    [challenge] = _claim("", lifecycle="check", state="OPEN")
    merged = _claim("", lifecycle="check", state="MERGED")

    assert challenge[2] == "status-claim" and challenge[5] == "Work.alpha"
    assert "lemonaid task assign t1 --to Work.beta" in challenge[6]
    assert ("challenge", "status-claim") not in _kinds(merged)


def test_a_running_ci_wait_does_not_hide_a_contradicted_status():
    [challenge] = _claim("merge", state="OPEN", draft="true", checks="pending", head="abc")

    assert challenge[:3] == ("challenge", "t1", "status-claim")
