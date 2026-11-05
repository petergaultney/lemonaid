import os
import threading
import time

import pytest

from lemonaid.watch import pr_activity, pr_changes, pr_poller

_KEY = ("o/r", 12)


def _repository(head: str, check: str = "COMPLETED", state: str = "OPEN") -> dict:
    rollup = {
        "contexts": {
            "pageInfo": {"hasNextPage": False},
            "nodes": [
                {
                    "__typename": "CheckRun",
                    "name": "tests",
                    "status": check,
                    "conclusion": "SUCCESS" if check == "COMPLETED" else None,
                    "isRequired": True,
                }
            ],
        }
    }
    return {
        "visibility": "PRIVATE",
        "pullRequest": {
            "headRefOid": head,
            "baseRefName": "main",
            "state": state,
            "isDraft": False,
            "reviewDecision": None,
            "mergeable": "MERGEABLE",
            "commits": {"nodes": [{"commit": {"oid": head, "statusCheckRollup": rollup}}]},
            "reviewThreads": {"nodes": []},
            "assignees": {"nodes": []},
            "reviews": {"nodes": []},
            "comments": {"nodes": []},
        },
    }


@pytest.fixture
def github(monkeypatch):
    """The fingerprint GitHub reports for _KEY, and every full read made."""
    state = {"fingerprint": "one", "repository": _repository("a" * 40), "reads": []}

    def fingerprints(keys):
        return {key: state["fingerprint"] for key in keys}

    def read(repo, number):
        state["reads"].append((repo, number))
        return state["repository"]

    monkeypatch.setattr(pr_changes, "fingerprints", fingerprints)
    monkeypatch.setattr(pr_activity, "read", read)
    return state


def test_many_watchers_share_one_read_until_the_pr_changes(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller.interested(*_KEY, "lemon-b")
    pr_poller._cycle(time.time())
    pr_poller._cycle(time.time())
    assert github["reads"] == [_KEY]
    assert pr_poller.snapshot(*_KEY) == github["repository"]

    github["fingerprint"] = "two"
    pr_poller._cycle(time.time())
    assert github["reads"] == [_KEY, _KEY]


def test_a_pr_with_checks_running_is_read_again_sooner(github, monkeypatch):
    monkeypatch.setattr(pr_poller, "_INTEREST", pr_poller._REFRESH)
    github["repository"] = _repository("a" * 40, check="IN_PROGRESS")
    pr_poller.interested(*_KEY, "lemon-a")
    now = time.time()
    pr_poller._cycle(now)
    pr_poller._cycle(now + pr_poller._INTERVAL)
    assert len(github["reads"]) == 1

    pr_poller._cycle(now + pr_poller._CHECKS_REFRESH - 1)
    assert len(github["reads"]) == 1

    pr_poller._cycle(now + pr_poller._CHECKS_REFRESH + 1)
    assert len(github["reads"]) == 2


def test_a_merged_pr_is_not_read_again_until_it_changes(github, monkeypatch):
    monkeypatch.setattr(pr_poller, "_REFRESH", 0)
    github["repository"] = _repository("a" * 40, state="MERGED")
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    pr_poller._cycle(time.time())
    assert len(github["reads"]) == 1


def test_an_unchanged_pr_is_read_again_after_the_refresh_period(github, monkeypatch):
    monkeypatch.setattr(pr_poller, "_REFRESH", 0)
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    pr_poller._cycle(time.time())
    assert len(github["reads"]) == 2


def test_a_pr_nobody_watches_lately_is_not_read(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time() + pr_poller._INTEREST + 1)
    assert github["reads"] == []


def _age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_a_stale_snapshot_is_read_from_the_file_while_the_poller_lives(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)

    assert pr_poller.snapshot(*_KEY) is None
    assert pr_poller.read(*_KEY) == github["repository"]
    assert github["reads"] == [_KEY]


def test_a_snapshot_the_live_poller_cannot_confirm_reads_as_a_failure(github, monkeypatch):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._BEHIND + 1)
    monkeypatch.setattr(pr_changes, "fingerprints", lambda keys: {})
    pr_poller._cycle(time.time())

    assert pr_poller.read(*_KEY) is None
    assert github["reads"] == [_KEY]


def test_a_stale_snapshot_sends_the_reader_to_github_once_the_poller_dies(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)
    _age(pr_poller._heartbeat_path(), pr_poller._STALE + 1)

    assert pr_poller.read(*_KEY) == github["repository"]
    assert len(github["reads"]) == 2


def test_a_pr_nobody_watches_is_read_from_github_though_the_poller_lives(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)
    _age(pr_poller._interest_root() / "o/r/12/lemon-a", pr_poller._INTEREST + 1)

    assert pr_poller.read(*_KEY) == github["repository"]
    assert len(github["reads"]) == 2


def test_unchanged_snapshots_are_confirmed_before_the_full_reads(github, monkeypatch):
    other = ("o/r", 13)
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller.interested(*other, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)
    fresh_during_read = []

    def fingerprints(keys):
        return {_KEY: "one", other: "changed"}

    def read(repo, number):
        fresh_during_read.append(pr_poller.snapshot(*_KEY) is not None)
        return github["repository"]

    monkeypatch.setattr(pr_changes, "fingerprints", fingerprints)
    monkeypatch.setattr(pr_activity, "read", read)
    pr_poller._cycle(time.time())

    assert fresh_during_read == [True]


def test_a_scout_reads_the_pollers_snapshot_without_asking_github(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())

    snapshot = pr_activity.fetch(*_KEY, (), source=pr_poller.read)

    assert snapshot and snapshot.head == "a" * 40
    assert github["reads"] == [_KEY]


def test_a_head_read_from_github_is_never_followed_by_an_older_snapshot(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)
    _age(pr_poller._heartbeat_path(), pr_poller._STALE + 1)
    github["repository"] = _repository("b" * 40)

    assert pr_poller.read(*_KEY)["pullRequest"]["headRefOid"] == "b" * 40
    pr_poller._beat()
    _age(pr_poller._snapshot_path(*_KEY), pr_poller._STALE + 1)
    assert pr_poller.read(*_KEY)["pullRequest"]["headRefOid"] == "b" * 40


def test_slow_github_reads_never_make_the_live_poller_look_dead(github, monkeypatch):
    monkeypatch.setattr(pr_poller, "_BEAT", 0.01)
    monkeypatch.setattr(pr_poller, "_STALE", 0.1)
    monkeypatch.setattr(pr_poller, "_BEHIND", 60)
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    _age(pr_poller._snapshot_path(*_KEY), 1)
    stop = threading.Event()
    beating = threading.Thread(target=pr_poller._keep_beating, args=(stop,), daemon=True)
    beating.start()
    seen = []

    def slow_fingerprints(keys):
        time.sleep(0.3)  # three times the heartbeat's lifetime
        seen.append(pr_poller.read(*_KEY))
        return {}

    monkeypatch.setattr(pr_changes, "fingerprints", slow_fingerprints)
    try:
        pr_poller._cycle(time.time())
    finally:
        stop.set()
        beating.join()

    assert seen == [github["repository"]]
    assert github["reads"] == [_KEY]
