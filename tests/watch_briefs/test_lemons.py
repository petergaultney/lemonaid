import pytest

from lemonaid.brief import lemon_table
from lemonaid.inbox import db
from lemonaid.watch import briefs_events, briefs_orphans, lemon_liveness

from .shared import lemon, link


@pytest.fixture
def sessions(monkeypatch):
    live = {"s-child", "s-other"}
    monkeypatch.setattr(briefs_orphans, "live_sessions", lambda socket: frozenset(live))
    return live


@pytest.fixture
def grove(sessions, tmp_path):
    parent, _ = lemon("parent", channel="codex:parent", session="s-parent")
    child, child_path = lemon("child", channel="codex:child", session="s-child")
    other, other_path = lemon("other", channel="codex:other", session="s-other")
    link(child, parent)
    sessions.add("s-parent")
    return parent, child, child_path, other, other_path, tmp_path / "state"


def _watch(grove, rows=(), to=frozenset({"merge", "done"}), needs=True):
    return briefs_events.open_watch(grove[5], grove[0], "me", 0, to, rows=tuple(rows), needs=needs)


def _poll(w):
    sent = []
    briefs_events.poll(w, sent.append)
    return sent


def _set_status(path, state):
    path.write_text(path.read_text().replace("Status: working", f"Status: {state}"))


def _mark_exited(channel, stamp):
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = json_set(metadata, '$.exited_at', ?, "
            "'$.exit_reason', 'logout') WHERE channel = ?",
            (stamp, channel),
        )
        conn.commit()


def test_row_for_a_non_child_reports_its_status_and_needs_changes(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove, [lemon_table.Row(other)])
    _set_status(other_path, "done")
    assert _poll(w) == [f"{other}: Status: none -> done ({other_path})"]
    assert _poll(w) == []


def test_non_child_without_a_row_is_not_watched(grove):
    _, _, _, _, other_path, _ = grove
    w = _watch(grove)
    _set_status(other_path, "done")
    assert _poll(w) == []


def test_row_resolves_a_brief_name(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove, [lemon_table.Row("other")])
    _set_status(other_path, "merge")
    assert _poll(w) == [f"{other}: Status: none -> merge ({other_path})"]


def test_row_customizes_a_childs_wake_statuses(grove):
    _, child, child_path, _, _, _ = grove
    w = _watch(grove, [lemon_table.Row(child, watch=("blocked",))])
    _set_status(child_path, "done")
    assert _poll(w) == []
    child_path.write_text(child_path.read_text().replace("Status: done", "Status: blocked"))
    assert _poll(w) == [f"{child}: Status: done -> blocked ({child_path})"]


def test_row_can_leave_needs_out(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove, [lemon_table.Row(other, watch=("done",))])
    other_path.write_text(other_path.read_text().replace("\n\n", "\n\n- pick one\n\n", 1))
    assert _poll(w) == []


def test_needs_change_wakes_by_default(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove, [lemon_table.Row(other)])
    other_path.write_text(other_path.read_text().rstrip() + "\n- pick a colour\n")
    assert "Needs: pick a colour" in _poll(w)[0]


def test_a_gone_session_is_reported_once_per_exit(grove, sessions):
    _, child, child_path, _, _, _ = grove
    w = _watch(grove)
    sessions.discard("s-child")
    assert _poll(w) == [f"{child}: its tmux session s-child is gone; Status: none ({child_path})"]
    assert _poll(w) == []
    assert _poll(_watch(grove)) == []
    sessions.add("s-child")
    assert _poll(w) == []
    sessions.discard("s-child")
    assert len(_poll(w)) == 1


def test_a_lemon_already_gone_at_first_watch_is_taken_as_seen(grove, sessions):
    sessions.discard("s-child")
    w = _watch(grove)
    assert _poll(w) == []


def test_a_recorded_exit_is_reported_once_per_exit(grove):
    _, child, child_path, _, _, _ = grove
    w = _watch(grove)
    _mark_exited("codex:child", 100.0)
    assert _poll(w) == [f"{child}: its harness exited (logout); Status: none ({child_path})"]
    assert _poll(w) == []
    _mark_exited("codex:child", 200.0)
    assert len(_poll(w)) == 1


def test_a_row_lemon_that_exits_is_reported(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove, [lemon_table.Row(other, watch=("blocked",))])
    _mark_exited("codex:other", 100.0)
    assert _poll(w) == [f"{other}: its harness exited (logout); Status: none ({other_path})"]


def test_a_done_lemon_whose_session_is_gone_is_normal(grove, sessions):
    _, _, child_path, _, _, _ = grove
    _set_status(child_path, "done")
    w = _watch(grove)
    sessions.discard("s-child")
    _mark_exited("codex:child", 100.0)
    assert _poll(w) == []


def test_a_deaf_lemon_is_reported_once_after_it_stays_deaf(grove, monkeypatch):
    _, child, child_path, _, _, _ = grove
    clock, armed = [0.0], [True]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lemon_liveness.waiter, "is_armed", lambda inbox: armed[0])
    w = _watch(grove)
    armed[0] = False
    assert _poll(w) == []
    clock[0] = 30.0
    assert _poll(w) == []
    clock[0] = 61.0
    (sent,) = _poll(w)
    assert sent.startswith(f"{child}: it is idle with no inbox waiter")
    assert sent.endswith(f"Status: none ({child_path})")
    clock[0] = 120.0
    assert _poll(w) == []


def test_a_newly_listed_lemon_already_in_a_wake_status_is_taken_as_seen(grove):
    _, _, _, other, other_path, _ = grove
    w = _watch(grove)
    _set_status(other_path, "done")
    w.rows = (lemon_table.Row(other),)
    assert _poll(w) == []
