from lemonaid.tasks.inspection import pr_facts
from lemonaid.watch import pr_activity

_URL = "https://github.com/o/r/pull/9"


def _values(found) -> dict[str, tuple[str, str]]:
    return {f["field"]: (f["value"], f["availability"]) for f in found}


def test_mergeable_unresolved_threads_and_the_users_verdict_are_facts():
    snap = pr_activity.Snapshot(
        "abc", "OPEN", False, "", [], "main", "CONFLICTING", [],
        user_verdict="APPROVED", unresolved=("other sam", "user me Work"),
    )  # fmt: skip
    found = _values(pr_facts.facts(_URL, 0.0, lambda _key: snap))

    assert found["mergeable"] == ("CONFLICTING", "known")
    assert found["unresolved"] == ("other sam\nuser me Work", "known")
    assert found["user_verdict"] == ("APPROVED", "known")


def test_what_an_old_snapshot_never_read_is_unknown_and_no_snapshot_is_unavailable():
    old = pr_activity.Snapshot(
        "abc", "OPEN", False, "", [], "main", "MERGEABLE", [], user_verdict=None, unresolved=None
    )
    found = _values(pr_facts.facts(_URL, 0.0, lambda _key: old))

    assert found["user_verdict"][1] == found["unresolved"][1] == "unknown"
    assert {a for _, a in _values(pr_facts.facts(_URL, 0.0, lambda _key: None)).values()} == {
        "unavailable"
    }
