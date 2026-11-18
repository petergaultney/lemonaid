import os
import time

import pytest

from lemonaid.brief import attached
from lemonaid.brief.handoff import transfer
from lemonaid.inbox import db
from lemonaid.watch import briefs_events, briefs_orphans, lemon_liveness

from .shared import lemon, link


@pytest.fixture
def family(monkeypatch, tmp_path):
    monkeypatch.setattr(briefs_orphans, "live_sessions", lambda socket: frozenset({"s-child"}))
    parent, _ = lemon("parent")
    child, child_path = lemon("child", channel="codex:child", session="s-child")
    link(child, parent)
    os.utime(child_path, (0, 0))  # written before it was attached
    return parent, child, child_path, tmp_path / "state"


def _watch(parent, state_dir):
    return briefs_events.open_watch(state_dir, parent, "me", 0)


def _poll(w):
    sent = []
    briefs_events.poll(w, sent.append)
    return sent


def test_a_child_idle_with_its_brief_untouched_is_reported_once(family, monkeypatch):
    parent, child, child_path, state_dir = family
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    w = _watch(parent, state_dir)  # deaf: no waiter yet
    monkeypatch.setattr(lemon_liveness.waiter, "is_armed", lambda mailbox: True)
    assert _poll(w) == []
    clock[0] = 61.0
    assert _poll(w) == [
        f"{child}: it went idle without touching its brief since it started; "
        f"Status: none ({child_path})"
    ]
    clock[0] = 120.0
    assert _poll(w) == []


def test_a_child_that_edited_its_brief_is_not_reported(family, monkeypatch):
    parent, _, child_path, state_dir = family
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    w = _watch(parent, state_dir)
    monkeypatch.setattr(lemon_liveness.waiter, "is_armed", lambda mailbox: True)
    child_path.write_text(child_path.read_text() + "\nTook it up.\n")
    clock[0] = 61.0
    assert _poll(w) == []


def test_a_brief_handed_to_a_listening_successor_is_not_reported(family, monkeypatch):
    parent, _, child_path, state_dir = family
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lemon_liveness.waiter, "is_armed", lambda mailbox: True)
    child_path.write_text(child_path.read_text().replace("## Now\n", "## Now\n\nTook it up.\n"))
    os.utime(child_path, (0, 0))
    w = _watch(parent, state_dir)
    with db.connect() as conn:
        db.add(conn, "codex:successor", "", name="successor")
        transfer.move(conn, str(child_path), "codex:child", "codex:successor", "test")
        conn.commit()
    assert _poll(w) == []
    clock[0] = 61.0
    assert _poll(w) == []


def test_a_brief_no_lemon_takes_up_is_reported_once_after_the_grace(family, monkeypatch):
    parent, _, _, state_dir = family
    late, late_path = lemon("late")
    link(late, parent)
    with db.connect() as conn:
        attached.attach_pending(conn, "", "", late_path, (), token="never-recorded")
    w = _watch(parent, state_dir)
    assert _poll(w) == []

    started = time.time()
    monkeypatch.setattr(lemon_liveness.time, "time", lambda: started + 301)
    (sent,) = _poll(w)
    assert sent.startswith(f"{late}: no lemon has taken up its brief since ")
    assert _poll(w) == []


def test_a_brief_left_waiting_from_long_ago_is_not_reported(family, monkeypatch):
    parent, _, _, state_dir = family
    old, old_path = lemon("old")
    link(old, parent)
    with db.connect() as conn:
        attached.attach_pending(conn, "", "", old_path, (), token="never-recorded")
    w = _watch(parent, state_dir)
    started = time.time()
    monkeypatch.setattr(lemon_liveness.time, "time", lambda: started + 6 * 86400)
    assert _poll(w) == []
