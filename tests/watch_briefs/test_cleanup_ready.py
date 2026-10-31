import pytest

from lemonaid.brief import child_place, children_cli
from lemonaid.watch import briefs_events, cleanup_ready

from .shared import lemon, link, open_watch, poll


@pytest.fixture
def attached(monkeypatch):
    """Clients attached per tmux session, as the waiter's one tmux call would see them."""
    clients = {"s-child": 1}
    monkeypatch.setattr(cleanup_ready, "_EVERY", 0)
    monkeypatch.setattr(
        children_cli,
        "holds_world",
        lambda: child_place.World(set(clients), dict(clients), (), {}, ()),
    )
    return clients


@pytest.fixture
def held(tmp_path, attached):
    parent, _ = lemon("parent", channel="codex:parent")
    child, path = lemon("child", channel="codex:child", session="s-child")
    link(child, parent)
    return parent, child, path, tmp_path / "watch-state"


def _done(path):
    path.write_text(path.read_text().replace("Status: working", "Status: done"))


def test_a_child_held_when_done_is_reported_once_when_its_client_leaves(held, attached):
    _, child, path, _ = held
    w = open_watch(held)
    _done(path)
    assert poll(w) == [f"{child}: Status: none -> done ({path})"]
    assert poll(w) == []
    attached["s-child"] = 0
    assert poll(w) == [
        f"{child}: cleanup ready, nothing holds its place now (held by: a client is attached"
        f" to s-child); Status: done ({path})"
    ]
    assert poll(w) == []
    assert poll(open_watch(held)) == []


def test_the_hold_survives_a_rearm(held, attached):
    _, child, path, _ = held
    _done(path)
    poll(open_watch(held))
    attached["s-child"] = 0
    [message] = poll(open_watch(held))
    assert message.startswith(f"{child}: cleanup ready")


def test_a_child_ready_when_done_or_already_cleaned_gets_no_second_report(held, attached):
    _, _, path, _ = held
    attached["s-child"] = 0
    w = open_watch(held)
    _done(path)
    assert len(poll(w)) == 1
    del attached["s-child"]
    assert poll(w) == []


def test_a_held_child_cleaned_up_without_its_client_leaving_is_not_reported(held, attached):
    _, _, path, _ = held
    w = open_watch(held)
    _done(path)
    poll(w)
    del attached["s-child"]
    assert poll(w) == []


def test_without_done_among_the_wake_statuses_nothing_is_reported(held, attached):
    _, _, path, _ = held
    w = open_watch(held, to=frozenset({"merge"}))
    _done(path)
    assert poll(w) == []
    attached["s-child"] = 0
    assert poll(w) == []


def test_the_report_carries_the_cleanup_ready_note(held, attached):
    parent, _, path, state_dir = held
    w = briefs_events.open_watch(
        state_dir, parent, "me", 0, notes=lambda: {"child.cleanup_ready": "Toss it now."}
    )
    _done(path)
    poll(w)
    attached["s-child"] = 0
    [message] = poll(w)
    assert message.endswith("- child.cleanup_ready: Toss it now.")


def test_a_rearm_within_the_interval_does_not_check_again(held, attached, monkeypatch):
    parent, child, path, state_dir = held
    _done(path)
    reads = []
    world = children_cli.holds_world
    monkeypatch.setattr(cleanup_ready, "_EVERY", 30.0)
    monkeypatch.setattr(children_cli, "holds_world", lambda: reads.append(1) or world())
    cursor = state_dir / "cleanup.json"
    state_dir.mkdir(parents=True)
    cleanup_ready.due(cleanup_ready.open_tracker(cursor), parent, {child}, 1000.0)
    assert cleanup_ready.due(cleanup_ready.open_tracker(cursor), parent, {child}, 1010.0) == {}
    assert len(reads) == 1
    attached["s-child"] = 0
    assert cleanup_ready.due(cleanup_ready.open_tracker(cursor), parent, {child}, 1030.0) == {
        child: ["a client is attached to s-child"]
    }
    assert len(reads) == 2


def test_a_failed_session_read_keeps_the_hold_until_tmux_answers(held, attached, monkeypatch):
    _, child, path, _ = held
    w = open_watch(held)
    _done(path)
    poll(w)
    known = children_cli.holds_world
    monkeypatch.setattr(
        children_cli, "holds_world", lambda: child_place.World(None, {}, (), {}, ())
    )
    assert poll(w) == []
    monkeypatch.setattr(children_cli, "holds_world", known)
    attached["s-child"] = 0
    [message] = poll(w)
    assert message.startswith(f"{child}: cleanup ready")


def test_outside_tmux_a_child_held_by_its_own_child_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup_ready, "_EVERY", 0)
    monkeypatch.setattr(
        children_cli, "holds_world", lambda: child_place.World(None, None, (), {}, ())
    )
    parent, _ = lemon("parent", channel="cmux:parent")
    child, path = lemon("child", channel="cmux:child")
    grandchild, grandchild_path = lemon("grandchild", channel="cmux:grandchild")
    link(child, parent)
    link(grandchild, child)
    w = briefs_events.open_watch(tmp_path / "watch-state", parent, "me", 0)
    _done(path)
    assert poll(w) == [f"{child}: Status: none -> done ({path})"]
    _done(grandchild_path)
    [message] = poll(w)
    assert message.startswith(f"{child}: cleanup ready") and "grandchild" in message
