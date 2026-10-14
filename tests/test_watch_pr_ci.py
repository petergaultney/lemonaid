"""CI completion watches through the public waiting loop."""

import json

import pytest

from lemonaid.watch import delivery, merge_health, pr_activity, pr_comments, pr_wait

_HEAD = "a" * 40
_NEXT = "b" * 40


def _snap(outcomes=(), *, head=_HEAD, state="OPEN", comments=()):
    return pr_activity.Snapshot(
        head,
        state,
        True,
        "",
        list(comments),
        "main",
        "CONFLICTING",
        [pr_activity.Check(str(i), False, outcome) for i, outcome in enumerate(outcomes)],
    )


def _wait(stem, snapshots, *, head=_HEAD, ci=True, comments=False, deliver=None, once=True):
    """Starts with cursors that show no comment and no CI result, as if the lemon has seen none."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    for suffix, value in (
        (".reported.json", []),
        (".merge.json", merge_health.Seen("", "")._asdict()),
    ):
        if not stem.with_suffix(suffix).exists():
            stem.with_suffix(suffix).write_text(json.dumps(value))
    feed, sent = iter(snapshots), []
    pr_wait.wait(
        lambda: next(feed), 90, 0, head, comments, deliver or sent.append, once, stem, ci=ci
    )
    return sent


@pytest.mark.parametrize("outcome", ["passed", "failed"])
def test_ci_completion_and_rearm_without_repeats(tmp_path, outcome):
    stem = tmp_path / "pr"
    done = _snap([outcome, "passed"])
    sent = _wait(stem, [_snap([outcome, "pending"]), done, done])
    assert len(sent) == 1
    assert sent[0].startswith(f"PR #90 CI {outcome} at {_HEAD[:10]}")
    assert "conflicts" not in sent[0]
    assert _wait(stem, [done, _snap(head=_NEXT)], head=_HEAD[:7]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]


def test_no_checks_is_not_a_ci_completion(tmp_path):
    snaps = [_snap(), _snap(["pending"]), _snap(["passed"]), _snap(["passed"])]
    assert _wait(tmp_path / "pr", snaps) == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_new_push_mid_run_uses_only_the_new_heads_checks(tmp_path):
    stem = tmp_path / "pr"
    assert _wait(stem, [_snap(["pending"]), _snap(["pending"], head=_NEXT)]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]
    assert _wait(stem, [_snap(["passed"], head=_NEXT)] * 2, head=_NEXT) == [
        f"PR #90 CI passed at {_NEXT[:10]}"
    ]


def test_enabling_ci_after_a_comment_reports_completion(tmp_path):
    stem = tmp_path / "pr"
    comment = pr_comments.Comment("c1", "PR", "peter", "fix this")
    done = _snap(["passed"], comments=[comment])._replace(mergeable="MERGEABLE")
    assert "new comment" in _wait(stem, [done], ci=False, comments=True)[0]
    assert _wait(stem, [done, done], comments=True) == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_ci_and_comments_report_failure_once_together(tmp_path):
    message = _wait(tmp_path / "pr", [_snap(["failed"])], comments=True)[0]
    assert message.count("CI failed") == 1
    assert "conflicts with main" in message


def test_failure_already_reported_by_comments_is_not_repeated_with_ci(tmp_path):
    stem = tmp_path / "pr"
    done = _snap(["failed"])._replace(mergeable="MERGEABLE")
    assert "CI failed" in _wait(stem, [done], ci=False, comments=True)[0]
    assert _wait(stem, [done, _snap(head=_NEXT)]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]


def test_failed_delivery_leaves_ci_completion_for_rearm(tmp_path):
    def fail(message):
        raise delivery.Failed("queue failed")

    stem = tmp_path / "pr"
    with pytest.raises(delivery.Failed):
        _wait(stem, [_snap(["passed"])] * 2, deliver=fail)
    assert _wait(stem, [_snap(["passed"])] * 2) == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_continuous_ci_watch_reports_each_head_once(tmp_path):
    sent = []

    def deliver(message):
        sent.append(message)
        if len(sent) == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _wait(
            tmp_path / "pr",
            [
                _snap(["passed"]),
                _snap(["passed"]),
                _snap(["pending"], head=_NEXT),
                _snap(["failed"], head=_NEXT),
            ],
            deliver=deliver,
            once=False,
        )
    assert sent[0] == f"PR #90 CI passed at {_HEAD[:10]}"
    assert sent[1] == f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    assert sent[2].startswith(f"PR #90 CI failed at {_NEXT[:10]}")


def test_closed_pr_does_not_report_ci(tmp_path):
    assert _wait(tmp_path / "pr", [_snap(["passed"], state="MERGED")]) == ["PR #90 is now MERGED"]


def test_ci_follows_required_check_results_after_all_checks_finish(tmp_path):
    done = _snap(["passed", "failed"])._replace(
        checks=[
            pr_activity.Check("gate", True, "passed"),
            pr_activity.Check("optional", False, "failed"),
        ]
    )
    assert _wait(tmp_path / "pr", [done, done]) == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_pass_waits_for_a_stable_set_of_checks(tmp_path):
    """The first jobs of a workflow pass before its other jobs have been queued."""
    sent = _wait(
        tmp_path / "pr", [_snap(["passed"] * 2), _snap(["passed"] * 3), _snap(["passed"] * 3)]
    )
    assert sent == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_early_pass_does_not_hide_the_real_one_after_rearm(tmp_path):
    stem = tmp_path / "pr"
    assert len(_wait(stem, [_snap(["passed"] * 2)] * 2)) == 1
    rearmed = [_snap(["passed"] * 2 + ["pending"]), _snap(["passed"] * 3), _snap(["passed"] * 3)]
    assert _wait(stem, rearmed) == [f"PR #90 CI passed at {_HEAD[:10]}"]


def test_pending_checks_without_ci_warn_at_arm_time_and_in_the_first_event(tmp_path, capsys):
    sent = _wait(tmp_path / "pr", [_snap(["pending"]), _snap(["pending"], head=_NEXT)], ci=False)
    assert "add --ci" in capsys.readouterr().err
    assert sent[0].startswith("PR #90 has checks pending; add --ci")
    assert f"head moved {_HEAD[:10]}" in sent[0]


def test_pending_checks_with_ci_do_not_warn(tmp_path, capsys):
    _wait(tmp_path / "pr", [_snap(["pending"]), _snap(["passed"]), _snap(["passed"])])
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("outcomes", [[], ["passed"], ["failed", "passed"]])
def test_finished_or_absent_checks_do_not_warn(tmp_path, capsys, outcomes):
    sent = _wait(tmp_path / "pr", [_snap(outcomes, head=_NEXT)], ci=False)
    assert capsys.readouterr().err == ""
    assert "add --ci" not in sent[0]
