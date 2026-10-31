import pytest

from lemonaid.tasks.checker import checker_input, corpus
from lemonaid.tasks.checker.default import rules

from ..shared import fact, idle, snapshot, task


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
            "assignment.acknowledged_at": "",
        }
    )


_NOT_STARTED = [fact("lemon", "Work.alpha", "attached", "false")]


def test_unstarted_child_gets_launch_grace_and_no_ack_accusation():
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


def test_attached_unacknowledged_idle_holder_is_asked_to_acknowledge_first():
    records = _evaluate(
        [
            task(
                **{
                    "assignment.acknowledged_at": "",
                    "assignment.attached_at": "2026-10-31T11:40:00Z",
                }
            )
        ],
        idle(),
    )

    assert _kinds(records) == [("challenge", "acknowledge")]


def test_acknowledgment_grace_starts_at_delivery_for_a_running_holder():
    records = _evaluate(
        [
            task(
                **{
                    "assignment.acknowledged_at": "",
                    "assignment.attached_at": "2026-10-31T10:00:00Z",
                    "assignment.delivered_at": "2026-10-31T11:58:00Z",
                }
            )
        ],
        idle(),
    )

    assert _kinds(records) == [("ok",), ("recheck",)]


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


def _ci(checks: str, delivered: str = "") -> list[dict[str, str]]:
    return [
        *idle(),
        fact("pr", _URL, "checks", checks),
        fact("pr", _URL, "head", "abc"),
        fact("pr", _URL, "release_delivered_at", delivered),
    ]


def test_wait_records_carry_type_before_evidence():
    assert _evaluate([task(subject_url=_URL)], _ci("pending")) == [
        ("wait", "t1", "progress", "waiting-for-ci", f"{_URL}@abc", _SOON, "CI is running")
    ]
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


def test_finished_ci_is_the_holders_move_only_after_delivery_and_grace():
    undelivered = _evaluate([task(subject_url=_URL)], _ci("passed"))
    recent = _evaluate([task(subject_url=_URL)], _ci("passed", "2026-10-31T11:59:30Z"))
    overdue = _evaluate([task(subject_url=_URL)], _ci("passed", "2026-10-31T11:30:00Z"))

    assert _kinds(undelivered) == [("wait", "progress")]
    assert undelivered[0][3] == "release-notification"
    assert _kinds(recent) == [("ok",), ("recheck",)]
    assert overdue == [
        (
            "challenge",
            "t1",
            "ci-result",
            f"{_URL}@abc:passed",
            "brief",
            "Work.alpha",
            "CI passed on abc",
        ),
    ]


def test_a_task_with_ci_absent_is_judged_on_idleness_alone():
    assert _kinds(_evaluate([task(subject_url=_URL)], _ci("none"))) == [("challenge", "progress")]


def _child(lifecycle: str, finding: str = "", delivered: str = "") -> list[dict[str, str]]:
    return [
        *idle(),
        fact("task", "t1", "cycle", ""),
        fact("task", "t2", "lifecycle", lifecycle),
        *([fact("task", "t2", "finding", finding)] if finding else []),
        fact("task", "t2", "release_delivered_at", delivered),
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


def test_a_closed_dependency_asks_for_its_result_once_its_release_is_delivered():
    held = task(**{"dependency.t2": "pending"})

    assert _evaluate([held], _child("closed"))[0][3] == "release-notification"
    assert _evaluate([held], _child("closed", delivered="2026-10-31T11:00:00Z")) == [
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
