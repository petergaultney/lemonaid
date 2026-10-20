import os
import time

import pytest

from lemonaid.watch import pr_activity, pr_changes, pr_poller

_KEY = ("o/r", 12)


def _repository(head: str, check: str = "COMPLETED") -> dict:
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
            "state": "OPEN",
            "isDraft": False,
            "reviewDecision": None,
            "mergeable": "MERGEABLE",
            "commits": {"nodes": [{"commit": {"oid": head, "statusCheckRollup": rollup}}]},
            "reviewThreads": {"nodes": []},
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


def test_a_pr_with_checks_running_is_read_every_cycle(github):
    github["repository"] = _repository("a" * 40, check="IN_PROGRESS")
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    pr_poller._cycle(time.time())
    assert len(github["reads"]) == 2


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


def test_a_stale_snapshot_sends_the_reader_to_github(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())
    path = pr_poller._snapshot_path(*_KEY)
    old = time.time() - pr_poller._STALE - 1
    os.utime(path, (old, old))

    assert pr_poller.snapshot(*_KEY) is None
    assert pr_poller.read(*_KEY) == github["repository"]
    assert len(github["reads"]) == 2


def test_a_scout_reads_the_pollers_snapshot_without_asking_github(github):
    pr_poller.interested(*_KEY, "lemon-a")
    pr_poller._cycle(time.time())

    snapshot = pr_activity.fetch(*_KEY, (), source=pr_poller.read)

    assert snapshot and snapshot.head == "a" * 40
    assert github["reads"] == [_KEY]
