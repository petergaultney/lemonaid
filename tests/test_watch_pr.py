"""`lemonaid watch pr`: events, the state kept between waiters, and the CLI."""

import hashlib
import json
import os
import stat
import subprocess
import sys

import pytest

from lemonaid.watch import delivery, pr_activity, pr_wait

_HEAD = "a" * 40


def _snap(head=_HEAD, state="OPEN", draft=True, decision="", comments=()):
    return pr_activity.Snapshot(head, state, draft, decision, list(comments))


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


def test_state_files_are_named_like_the_standalone_waiters(tmp_path):
    expected = hashlib.sha1(b"o/r#90\0Author (X)").hexdigest()[:16]

    assert pr_wait.state_stem(tmp_path, "o/r", 90, "Author (X)") == tmp_path / expected
    assert (
        pr_wait.state_stem(tmp_path, "o/r", 90, "").name == hashlib.sha1(b"o/r#90").hexdigest()[:16]
    )


def test_a_push_is_reported_against_the_head_already_handled(stem):
    sent = _run_once(stem, [_snap(), _snap(head="b" * 40)])

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


def test_the_lemon_marker_and_pending_reviews_are_not_human():
    pr = {
        "reviewThreads": {
            "nodes": [
                {
                    "isResolved": False,
                    "isOutdated": False,
                    "path": "a",
                    "line": 1,
                    "comments": {
                        "nodes": [
                            {
                                "id": "1",
                                "body": "\N{LEMON}: mine",
                                "state": "SUBMITTED",
                                "author": {"login": "p", "__typename": "User"},
                            },
                            {
                                "id": "2",
                                "body": "draft",
                                "state": "PENDING",
                                "author": {"login": "p", "__typename": "User"},
                            },
                            {
                                "id": "3",
                                "body": "real",
                                "state": "SUBMITTED",
                                "author": {"login": "p", "__typename": "User"},
                            },
                        ]
                    },
                }
            ]
        },
        "reviews": {
            "nodes": [
                {
                    "id": "4",
                    "body": "lgtm",
                    "state": "APPROVED",
                    "author": {"login": "ci", "__typename": "Bot"},
                }
            ]
        },
        "comments": {"nodes": []},
    }

    assert [c.id for c in pr_activity._human_comments(pr)] == ["3"]


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
                            "state": "OPEN",
                            "isDraft": True,
                            "reviewDecision": None,
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


def test_cli_status_and_comments_needs_me(tmp_path, fake_gh):
    assert _cli(tmp_path, "--status", "90").stdout == "no waiter running\n"
    refused = _cli(tmp_path, "--wait", "90", "--comments")
    assert refused.returncode == 2
    assert "--comments needs --me" in refused.stderr
