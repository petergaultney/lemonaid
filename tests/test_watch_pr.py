"""`lemonaid watch pr`: events, the state kept between waiters, and the CLI."""

import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

from lemonaid.watch import delivery, lemon_signature, merge_health, pr_activity, pr_wait

_HEAD = "a" * 40


def _snap(
    head=_HEAD,
    state="OPEN",
    draft=True,
    decision="",
    comments=(),
    mergeable="MERGEABLE",
    checks=(),
):
    return pr_activity.Snapshot(
        head, state, draft, decision, list(comments), "main", mergeable, list(checks)
    )


def _check(name="test", required=False, outcome="passed"):
    return pr_activity.Check(name, required, outcome)


def _comment(i: str, body="please fix"):
    return pr_activity.Comment(i, "src/x.py:3", "peter", body)


@pytest.fixture
def stem(tmp_path):
    return pr_wait.state_stem(tmp_path / "state", "o/r", 90, "Author (X)")


def _run_once(stem, snaps, head=_HEAD, comments=True):
    stem.parent.mkdir(parents=True, exist_ok=True)
    feed, sent = iter(snaps), []
    pr_wait.wait(lambda: next(feed), 90, 0, head, comments, sent.append, True, stem)
    return sent


def test_state_files_keep_their_names(tmp_path):
    """Renaming them would make the next waiter for the same PR re-report what earlier ones did."""
    expected = hashlib.sha1(b"o/r#90\0Author (X)").hexdigest()[:16]

    assert pr_wait.state_stem(tmp_path, "o/r", 90, "Author (X)") == tmp_path / expected
    assert (
        pr_wait.state_stem(tmp_path, "o/r", 90, "").name == hashlib.sha1(b"o/r#90").hexdigest()[:16]
    )


def test_a_push_is_reported_against_the_head_already_handled(stem):
    sent = _run_once(stem, [_snap(), _snap(head="b" * 40)])

    assert sent == [f"PR #90 head moved {'a' * 10} -> {'b' * 10}"]


def test_an_abbreviated_head_matches_the_full_one(stem):
    sent = _run_once(stem, [_snap(), _snap(head="b" * 40)], head="a" * 10)

    assert sent == [f"PR #90 head moved {'a' * 10} -> {'b' * 10}"]


def test_a_merge_and_a_decision_are_reported(stem):
    sent = _run_once(stem, [_snap(), _snap(state="MERGED", decision="APPROVED")])

    assert sent == ["PR #90 is now MERGED; PR #90 review decision: APPROVED"]


def test_a_comment_handled_but_left_open_is_not_reported_after_a_rearm(stem):
    assert _run_once(stem, [_snap(comments=[_comment("c1")])])[0].startswith(
        "PR #90: 1 new comment(s) - peter (src/x.py:3): please fix"
    )
    sent = _run_once(
        stem,
        [
            _snap(comments=[_comment("c1")]),
            _snap(comments=[_comment("c1"), _comment("c2", "and this")]),
        ],
    )

    assert sent == ["PR #90: 1 new comment(s) - peter (src/x.py:3): and this"]


def test_a_draft_change_between_waiters_is_reported(stem):
    _run_once(stem, [_snap(comments=[_comment("c1")])])

    assert _run_once(stem, [_snap(draft=False, comments=[_comment("c1")])]) == [
        "PR #90 is now ready for review"
    ]


def test_a_failed_delivery_records_nothing(stem):
    stem.parent.mkdir(parents=True)

    def fail(message: str) -> None:
        raise delivery.Failed("codex queue failed (exit 1)")

    with pytest.raises(delivery.Failed):
        pr_wait.wait(lambda: _snap(comments=[_comment("c1")]), 90, 0, _HEAD, True, fail, True, stem)
    assert _run_once(stem, [_snap(comments=[_comment("c1")])])[0].startswith(
        "PR #90: 1 new comment(s)"
    )


def test_a_conflict_is_reported_once_per_head(stem):
    assert _run_once(stem, [_snap(mergeable="CONFLICTING")])[0].startswith(
        f"PR #90 conflicts with main at {'a' * 10}"
    )
    rearmed = _run_once(
        stem, [_snap(mergeable="CONFLICTING"), _snap(head="b" * 40, mergeable="CONFLICTING")]
    )

    assert rearmed[0].startswith(f"PR #90 head moved {'a' * 10} -> {'b' * 10}; PR #90 conflicts")


def test_an_unknown_mergeable_state_is_not_a_conflict():
    seen = merge_health.Seen("", "")

    assert merge_health.events(90, _snap(mergeable="UNKNOWN"), seen) == ([], seen)


def test_ci_is_reported_once_every_check_has_finished(stem):
    running = [_check("lint", outcome="failed"), _check("test", outcome="pending")]
    done = [_check("lint", outcome="failed"), _check("test")]

    sent = _run_once(stem, [_snap(checks=running), _snap(checks=done)], head="")

    assert sent == [
        f"PR #90 CI failed at {'a' * 10}: lint: read `gh pr checks 90`,"
        " fix it and push (or rerun a flaky job), then tell your reviewer"
    ]
    assert (
        merge_health.events(
            90, _snap(checks=done), merge_health.load(stem.with_suffix(".merge.json"))
        )[0]
        == []
    )


def test_only_required_checks_count_when_there_are_any():
    checks = [_check("allow-merge", required=True), _check("flaky", outcome="failed")]

    assert merge_health.events(90, _snap(checks=checks), merge_health.Seen("", ""))[0] == []


def test_a_reviewer_is_not_woken_for_conflicts_or_ci(stem):
    blocked = _snap(mergeable="CONFLICTING", checks=[_check(outcome="failed")])

    assert _run_once(stem, [blocked, _snap(head="b" * 40)], comments=False) == [
        f"PR #90 head moved {'a' * 10} -> {'b' * 10}"
    ]


def test_check_runs_and_status_contexts_are_read():
    nodes = [
        {
            "__typename": "CheckRun",
            "name": "a",
            "status": "IN_PROGRESS",
            "conclusion": None,
            "isRequired": False,
        },
        {
            "__typename": "CheckRun",
            "name": "b",
            "status": "COMPLETED",
            "conclusion": "TIMED_OUT",
            "isRequired": True,
        },
        {"__typename": "StatusContext", "context": "c", "state": "EXPECTED", "isRequired": False},
        {"__typename": "StatusContext", "context": "d", "state": "SUCCESS", "isRequired": False},
    ]

    assert [pr_activity._check(n) for n in nodes] == [
        _check("a", outcome="pending"),
        _check("b", required=True, outcome="failed"),
        _check("c", outcome="pending"),
        _check("d"),
    ]


_SIGNED_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "watch_pr_signed_comments.json"


def _fixture_ids(*signatures):
    pr = json.loads(_SIGNED_FIXTURE.read_text())["data"]["repository"]["pullRequest"]
    return [c.id for c in pr_activity._others_comments(pr, signatures)]


def test_only_comments_signed_by_me_or_a_legacy_signature_are_mine():
    assert _fixture_ids("Author (MotorHoe)", "Claude") == [
        "PRRC_teammate_signed",
        "PRRC_teammate_unsigned",
        "PRRC_human",
        "IC_prefix",
    ]


def test_without_a_legacy_signature_its_comments_are_reported():
    assert "PRRC_mine_legacy" in _fixture_ids("Author (MotorHoe)")


def test_a_bare_name_that_no_comment_is_signed_with_owns_nothing():
    assert _fixture_ids("support-katamari") == [
        "PRRC_mine",
        "PRRC_mine_legacy",
        "PRRC_teammate_signed",
        "PRRC_teammate_unsigned",
        "PRRC_human",
        "PRR_mine",
        "IC_prefix",
    ]


@pytest.mark.parametrize(
    ("body", "signed"),
    [
        ("\N{LEMON} Author (X): ok", True),
        ("  \N{LEMON}Author (X): ok", True),
        ("\N{LEMON}\N{VARIATION SELECTOR-16} Author (X): ok", True),
        ("\N{LEMON}: ok", False),
        ("\N{LEMON} Author (X) ok", False),
        ("Author (X): ok", False),
        ("\N{LEMON} Author (Y): ok", False),
    ],
)
def test_a_signature_follows_the_marker_and_ends_with_a_colon(body, signed):
    assert lemon_signature.is_signed(body, ["Author (X)"]) is signed


_FAKE_GH = """#!/bin/sh
if [ "$1" = repo ]; then echo o/r; exit 0; fi
cat "$FAKE_GH_SNAPSHOT"
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    snapshot = tmp_path / "snapshot.json"
    monkeypatch.setenv("FAKE_GH_SNAPSHOT", str(snapshot))
    return snapshot


def _write_snapshot(path, head):
    path.write_text(
        json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "headRefOid": head,
                            "baseRefName": "main",
                            "state": "OPEN",
                            "isDraft": True,
                            "reviewDecision": None,
                            "mergeable": "MERGEABLE",
                            "commits": {
                                "nodes": [{"commit": {"oid": head, "statusCheckRollup": None}}]
                            },
                            "reviewThreads": {"nodes": []},
                            "reviews": {"nodes": []},
                            "comments": {"nodes": []},
                        }
                    }
                }
            }
        )
    )


def _cli(tmp_path, *args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "lemonaid",
            "watch",
            "pr",
            *args,
            "--interval",
            "0.05",
            "--state-dir",
            str(tmp_path / "state"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_cli_once_reports_a_push_and_exits(tmp_path, fake_gh):
    _write_snapshot(fake_gh, "b" * 40)

    result = _cli(tmp_path, "--wait", "90", "--head", _HEAD, "--once")

    assert result.returncode == 0
    assert result.stdout == f"PR #90 head moved {'a' * 10} -> {'b' * 10}\n"


def test_cli_accepts_an_abbreviated_head_in_either_case(tmp_path, fake_gh):
    _write_snapshot(fake_gh, "b" * 40)

    result = _cli(tmp_path, "--wait", "90", "--head", "ABABABA", "--once")

    assert result.returncode == 0
    assert result.stdout == f"PR #90 head moved abababa -> {'b' * 10}\n"


@pytest.mark.parametrize("head", ["abcdef", "<head SHA>", "a" * 41])
def test_cli_refuses_a_head_that_is_not_a_sha_of_7_or_more_digits(tmp_path, fake_gh, head):
    refused = _cli(tmp_path, "--wait", "90", "--head", head, "--once")

    assert refused.returncode == 2
    assert "not a commit SHA" in refused.stderr


def test_cli_status_and_comments_needs_me(tmp_path, fake_gh):
    assert _cli(tmp_path, "--status", "90").stdout == "no waiter running\n"
    refused = _cli(tmp_path, "--wait", "90", "--comments")
    assert refused.returncode == 2
    assert "--comments needs --me" in refused.stderr


def test_cli_reports_others_comments_but_not_mine(tmp_path, fake_gh):
    fake_gh.write_text(_SIGNED_FIXTURE.read_text())

    result = _cli(
        tmp_path,
        "--wait",
        "90",
        "--head",
        "b" * 40,
        "--comments",
        "--me",
        "Author (MotorHoe)",
        "--legacy",
        "Claude",
        "--once",
    )

    assert result.returncode == 0
    assert result.stdout.startswith("PR #90: 4 new comment(s) - harrison (src/x.py:3): ")
    assert "Reviewer (StateJob)" in result.stdout
