"""A failed check on a head is reported once, until it passes in between."""

from lemonaid.watch import merge_health, pr_activity, roles

_HEAD = "a" * 40


def _snap(*checks):
    return pr_activity.Snapshot(_HEAD, "OPEN", False, "", [], "main", "MERGEABLE", list(checks))


def _check(outcome, finished=""):
    return pr_activity.Check("test", False, outcome, finished)


def _kinds(events):
    return [e.kind for e in events]


def test_a_new_run_failing_again_is_not_reported_again():
    first, seen = merge_health.events(
        1, _snap(_check("failed", "10:00")), merge_health.Seen("", "")
    )
    assert _kinds(first) == [roles.CI_FAILED]

    again, seen = merge_health.events(1, _snap(_check("failed", "10:00")), seen)
    assert again == []

    running, seen = merge_health.events(1, _snap(_check("pending")), seen)
    assert running == []

    second, seen = merge_health.events(1, _snap(_check("failed", "10:20")), seen)
    assert second == []


def test_a_failure_after_a_pass_is_reported_again():
    _, seen = merge_health.events(1, _snap(_check("failed", "10:00")), merge_health.Seen("", ""))
    _, seen = merge_health.events(1, _snap(_check("passed", "10:10")), seen)

    again, _ = merge_health.events(1, _snap(_check("failed", "10:20")), seen)

    assert _kinds(again) == [roles.CI_FAILED]


def test_a_rerun_that_passes_is_reported_when_ci_is_watched():
    _, seen = merge_health.events(1, _snap(_check("failed", "10:00")), merge_health.Seen("", ""))
    passing = _snap(_check("passed", "10:20"))

    _, seen = merge_health.events(1, passing, seen, ci=True)
    passed, _ = merge_health.events(1, passing, seen, ci=True)

    assert _kinds(passed) == [roles.CI_GREEN]
