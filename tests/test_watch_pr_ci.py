"""CI completion watches through the public waiting loop."""

import pytest

from lemonaid.watch import delivery, pr_activity, pr_comments, pr_wait

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
    feed, sent = iter(snapshots), []
    pr_wait.wait(
        lambda: next(feed), 90, 0, head, comments, deliver or sent.append, once, stem, ci=ci
    )
    return sent


@pytest.mark.parametrize("outcome", ["passed", "failed"])
def test_ci_completion_and_rearm_without_repeats(tmp_path, outcome):
    stem = tmp_path / "pr"
    done = _snap([outcome, "passed"])
    sent = _wait(stem, [_snap([outcome, "pending"]), done])
    assert len(sent) == 1
    assert sent[0].startswith(f"PR #90 CI {outcome} at {_HEAD[:10]}")
    assert "conflicts" not in sent[0]
    assert _wait(stem, [done, _snap(head=_NEXT)], head=_HEAD[:7]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]


def test_no_checks_is_not_a_ci_completion(tmp_path):
    assert _wait(tmp_path / "pr", [_snap(), _snap(["pending"]), _snap(["passed"])]) == [
        f"PR #90 CI passed at {_HEAD[:10]}"
    ]


def test_new_push_mid_run_uses_only_the_new_heads_checks(tmp_path):
    stem = tmp_path / "pr"
    assert _wait(stem, [_snap(["pending"]), _snap(["pending"], head=_NEXT)]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]
    assert _wait(stem, [_snap(["passed"], head=_NEXT)], head=_NEXT) == [
        f"PR #90 CI passed at {_NEXT[:10]}"
    ]


def test_enabling_ci_after_a_comment_reports_completion(tmp_path):
    stem = tmp_path / "pr"
    comment = pr_comments.Comment("c1", "PR", "peter", "fix this")
    done = _snap(["passed"], comments=[comment])._replace(mergeable="MERGEABLE")
    assert "new comment" in _wait(stem, [done], ci=False, comments=True)[0]
    assert _wait(stem, [done], comments=True) == [f"PR #90 CI passed at {_HEAD[:10]}"]


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
        _wait(stem, [_snap(["passed"])], deliver=fail)
    assert _wait(stem, [_snap(["passed"])]) == [f"PR #90 CI passed at {_HEAD[:10]}"]


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
    assert _wait(tmp_path / "pr", [done]) == [f"PR #90 CI passed at {_HEAD[:10]}"]
