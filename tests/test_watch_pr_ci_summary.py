"""API-shaped check pages through the shared standalone and unified PR detector."""

import copy
import json
from pathlib import Path

import pytest

from lemonaid.watch import merge_health, pr_activity, pr_events

_FIXTURE = Path(__file__).parent / "fixtures" / "watch_pr_failed_optional_check.json"


def _fetch(monkeypatch, *, paginated=False):
    repository = json.loads(_FIXTURE.read_text())["data"]["repository"]
    commit = repository["pullRequest"]["commits"]["nodes"][0]["commit"]
    contexts = commit["statusCheckRollup"]["contexts"]
    last = contexts["nodes"].pop() if paginated else None
    contexts["pageInfo"] = {"hasNextPage": paginated, "endCursor": "page-one"}
    calls = []

    def read(repo, number, query, after, oid):
        calls.append((after, oid))
        if not after:
            return copy.deepcopy(repository)

        assert (after, oid) == ("page-one", commit["oid"])
        return {
            "object": {
                "statusCheckRollup": {
                    "contexts": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [last],
                    }
                }
            }
        }

    monkeypatch.setattr(pr_activity, "_repository", read)
    snap = pr_activity.fetch("example/project", 90, ())
    assert snap is not None
    assert len(calls) == (2 if paginated else 1)
    return snap


@pytest.mark.parametrize("paginated", [False, True])
@pytest.mark.parametrize("comments,ci", [(True, False), (False, True), (True, True)])
def test_optional_failure_never_reports_pass(tmp_path, monkeypatch, paginated, comments, ci):
    snap = _fetch(monkeypatch, paginated=paginated)
    stem = tmp_path / "pr"
    passed = snap._replace(checks=[check._replace(outcome="passed") for check in snap.checks])
    sent = []
    # Arm on running checks so the completed snapshot must produce an event.
    pending = snap._replace(checks=[check._replace(outcome="pending") for check in snap.checks])
    pr_events.poll(stem, 90, pending, sent.append, comments=comments, ci=ci)
    for current in (snap, snap, passed, passed, snap):
        pr_events.poll(stem, 90, current, sent.append, comments=comments, ci=ci)
    assert sent[0].startswith(f"PR #90 CI failed at {snap.head[:10]}: optional plan:")
    assert len(sent) == (2 if ci else 1)
    if ci:
        assert sent[1] == f"PR #90 CI passed at {snap.head[:10]}"
    assert merge_health.load(stem.with_suffix(".merge.json")).stable == ""


@pytest.mark.parametrize(
    "conclusion,outcome",
    [
        ("SUCCESS", "passed"),
        ("NEUTRAL", "passed"),
        ("SKIPPED", "passed"),
        ("FAILURE", "failed"),
        ("ACTION_REQUIRED", "failed"),
        ("CANCELLED", "failed"),
        ("STALE", "failed"),
        ("STARTUP_FAILURE", "failed"),
        ("TIMED_OUT", "failed"),
        (None, "pending"),
        ("UNKNOWN_FUTURE_VALUE", "pending"),
    ],
)
def test_check_conclusion_mapping(monkeypatch, conclusion, outcome):
    snap = _fetch(monkeypatch)
    repository = json.loads(_FIXTURE.read_text())["data"]["repository"]
    nodes = repository["pullRequest"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"][
        "contexts"
    ]["nodes"]
    nodes[-1]["conclusion"] = conclusion
    monkeypatch.setattr(pr_activity, "_repository", lambda *args: repository)
    result = pr_activity.fetch("example/project", 90, ())
    assert result.checks[-1] == snap.checks[-1]._replace(outcome=outcome)


@pytest.mark.parametrize(
    "state,outcome",
    [
        ("SUCCESS", "passed"),
        ("FAILURE", "failed"),
        ("ERROR", "failed"),
        ("PENDING", "pending"),
        ("EXPECTED", "pending"),
        ("UNKNOWN_FUTURE_VALUE", "pending"),
    ],
)
def test_status_context_mapping(monkeypatch, state, outcome):
    repository = json.loads(_FIXTURE.read_text())["data"]["repository"]
    nodes = repository["pullRequest"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"][
        "contexts"
    ]["nodes"]
    nodes[-1] = {
        "__typename": "StatusContext",
        "context": "external",
        "state": state,
        "isRequired": False,
    }
    monkeypatch.setattr(pr_activity, "_repository", lambda *args: repository)
    snap = pr_activity.fetch("example/project", 90, ())
    assert snap.checks[-1] == pr_activity.Check("external", False, outcome)
