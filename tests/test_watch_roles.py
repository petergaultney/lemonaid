"""Which PR events wake a lemon, by its role on the PR."""

import pytest

from lemonaid.watch import pr_activity, pr_events, pr_wait, roles

_HEAD = "a" * 40


def _snap(head=_HEAD, draft=False, checks=(), mergeable="MERGEABLE", state="OPEN"):
    return pr_activity.Snapshot(
        head, state, draft, "", [], "main", mergeable, list(checks), "PRIVATE"
    )


@pytest.fixture
def poll(tmp_path):
    stem = pr_wait.state_stem(tmp_path, "o/r", 90, "Reviewer (X)")
    sent: list[str] = []

    def poll(snap, role):
        return pr_events.poll(stem, 90, snap, sent.append, wake=roles.wake(role, {}))

    poll(_snap(draft=True), roles.REVIEWER)
    return poll, sent


def test_a_reviewer_sleeps_through_ready_and_ci_and_hears_them_with_the_next_push(poll):
    poll, sent = poll
    failed = [pr_activity.Check("test", False, "failed")]

    assert not poll(_snap(draft=False), roles.REVIEWER)
    assert not poll(_snap(draft=False, checks=failed), roles.REVIEWER)
    assert sent == []

    assert poll(_snap(head="b" * 40, draft=False), roles.REVIEWER)
    [message] = sent
    assert message.startswith(
        "Seen without waking you: PR #90 is now ready for review; PR #90 CI failed"
    )
    assert message.endswith(f"PR #90 head moved {'a' * 10} -> {'b' * 10}")


def test_a_parent_wakes_only_when_the_pr_merges(poll):
    poll, sent = poll

    assert not poll(_snap(head="b" * 40), roles.PARENT)
    assert poll(_snap(head="b" * 40, state="MERGED"), roles.PARENT)
    assert sent[0].endswith("PR #90 is now MERGED")


def test_config_replaces_a_roles_whole_list():
    assert roles.wake(roles.PARENT, {roles.PARENT: frozenset({roles.HEAD})}) == {roles.HEAD}
    assert roles.wake(roles.AUTHOR, {roles.PARENT: frozenset()}) == roles.DEFAULT_WAKE["author"]


@pytest.mark.parametrize(
    ("explicit", "me", "own_output", "child", "role"),
    [
        ("parent", "Reviewer (X)", True, False, "parent"),
        ("", "Reviewer (X)", False, True, "reviewer"),
        ("", "Author (X)", True, True, "reviewer"),
        ("", "Author (X)", False, True, "parent"),
        ("", "Author (X)", False, False, "author"),
    ],
)
def test_derive(explicit, me, own_output, child, role):
    assert roles.derive(explicit, me, own_output, child) == role
