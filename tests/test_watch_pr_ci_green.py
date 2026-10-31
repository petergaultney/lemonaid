"""A pass after CI was seen running or failed wakes the author once, with or without `--ci`."""

import json

from lemonaid.watch import merge_health, pr_activity, pr_wait

_HEAD = "a" * 40
_NEXT = "b" * 40


def _snap(outcomes, *, head=_HEAD):
    return pr_activity.Snapshot(
        head,
        "OPEN",
        False,
        "",
        [],
        "main",
        "MERGEABLE",
        [pr_activity.Check(str(i), False, outcome) for i, outcome in enumerate(outcomes)],
    )


def _wait(stem, snapshots, *, head=_HEAD, ci=False, first=False):
    """With *first*, starts as a first waiter, which takes the current CI state as seen."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    cursors = [(".reported.json", [])]
    if not first:
        cursors.append((".merge.json", merge_health.Seen("", "")._asdict()))
    for suffix, value in cursors:
        if not stem.with_suffix(suffix).exists():
            stem.with_suffix(suffix).write_text(json.dumps(value))
    feed, sent = iter(snapshots), []
    pr_wait.wait(lambda: next(feed), 90, 0, head, True, sent.append, True, stem, ci=ci)
    return sent


def _green(head):
    return (
        f"PR #90 CI passed at {head[:10]}: check"
        " `gh pr view 90 --json mergeable,reviewDecision,isDraft`;"
        " if only your user's merge remains, set your brief's Status back to `merge`"
    )


def test_a_rerun_that_passes_wakes_the_author_once(tmp_path):
    stem = tmp_path / "pr"
    assert "CI failed" in _wait(stem, [_snap(["failed"])])[0]
    rerun = [_snap(["pending"]), _snap(["passed"]), _snap(["passed"])]
    assert _wait(stem, rerun) == [_green(_HEAD)]
    assert merge_health.load(stem.with_suffix(".merge.json")).awaiting == ""


def test_a_new_push_that_passes_wakes_the_author(tmp_path):
    stem = tmp_path / "pr"
    _wait(stem, [_snap(["failed"])])
    assert _wait(stem, [_snap([], head=_NEXT)]) == [
        f"PR #90 head moved {_HEAD[:10]} -> {_NEXT[:10]}"
    ]
    assert _wait(stem, [_snap(["passed"], head=_NEXT)] * 2, head=_NEXT) == [_green(_NEXT)]


def test_a_first_waiter_on_running_ci_hears_it_pass(tmp_path):
    snaps = [_snap(["pending"]), _snap(["passed"]), _snap(["passed"])]
    assert _wait(tmp_path / "pr", snaps, first=True) == [_green(_HEAD)]


def test_green_replaces_the_ci_pass_event(tmp_path):
    assert _wait(tmp_path / "pr", [_snap(["pending"])] + [_snap(["passed"])] * 2, ci=True) == [
        _green(_HEAD)
    ]


def test_a_pass_already_settled_or_on_a_draft_wakes_no_one():
    seen = merge_health.Seen("", "")
    for snap in (_snap(["passed"]),) * 3:
        messages, seen = merge_health.events(90, snap, seen)
        assert messages == []

    draft = _snap(["pending"])._replace(draft=True)
    _, seen = merge_health.events(90, draft, merge_health.Seen("", ""))
    for snap in (draft._replace(checks=_snap(["passed"]).checks),) * 2:
        messages, seen = merge_health.events(90, snap, seen)
        assert messages == []
    assert seen.awaiting == ""
