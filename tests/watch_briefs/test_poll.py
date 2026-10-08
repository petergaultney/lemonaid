import pytest

from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.watch import briefs_events, delivery

from .shared import lemon, link, open_watch, poll


@pytest.mark.parametrize(
    "state",
    ["waiting", "running", "blocked", "merge", "alert", "review", "approve", "done", "working"],
)
def test_each_status_transition_fires_once(family, state):
    _, child, path, _ = family
    before = "waiting" if state == "working" else "working"
    path.write_text(path.read_text().replace("Status: working", f"Status: {before}"))
    w = open_watch(family)
    path.write_text(path.read_text().replace(f"Status: {before}", f"Status: {state}"))
    assert poll(w) == [f"{child}: Status: {before} -> {state} ({path})"]
    assert poll(w) == []
    assert poll(open_watch(family)) == []


def test_ask_changes_and_removal_fire_even_while_working(family):
    _, child, path, _ = family
    w = open_watch(family)
    path.write_text(path.read_text() + "- pick a colour\n")
    assert poll(w) == [f"{child}: Status: working; Needs: pick a colour ({path})"]
    path.write_text(path.read_text().replace("pick a colour", "try the build"))
    assert "Needs: try the build" in poll(w)[0]
    path.write_text(path.read_text().replace("- try the build", "nothing"))
    assert "Needs: (none)" in poll(w)[0]
    assert poll(w) == []


@pytest.mark.parametrize("state", ["working", "done"])
def test_progress_and_formatting_edits_stay_quiet(family, state):
    _, _, path, _ = family
    path.write_text(
        path.read_text().replace("Status: working", f"Status: {state}") + "- make a choice\n"
    )
    w = open_watch(family)
    path.write_text(
        path.read_text().replace("- make a choice", "* make   a\n  choice")
        + "\n### Next\n\n- more progress\n"
    )
    assert poll(w) == []
    assert poll(open_watch(family)) == []


def test_rearm_reports_changes_between_waiters_without_duplicates(family):
    _, child, path, _ = family
    open_watch(family)
    path.write_text(
        path.read_text().replace("Status: working", "Status: merge") + "- merge the PR\n"
    )
    assert poll(open_watch(family)) == [
        f"{child}: Status: working -> merge; Needs: merge the PR ({path})"
    ]
    assert poll(open_watch(family)) == []


def test_new_children_are_reported_but_nonchildren_and_grandchildren_are_ignored(family):
    parent, child, _, _ = family
    unrelated, unrelated_path = lemon("unrelated")
    grandchild, grandchild_path = lemon("grandchild")
    link(grandchild, child)
    w = open_watch(family)
    unrelated_path.write_text(unrelated_path.read_text().replace("working", "blocked"))
    grandchild_path.write_text(grandchild_path.read_text().replace("working", "merge"))
    assert poll(w) == []
    new, new_path = lemon("new", "waiting")
    link(new, parent)
    assert poll(w) == [f"{new}: Status: waiting ({new_path})"]
    assert poll(open_watch(family)) == []


def test_missing_brief_and_unlink_do_not_fire_or_repeat_old_changes(family):
    parent, child, path, _ = family
    w = open_watch(family)
    original = path.read_text()
    path.unlink()
    assert poll(w) == []
    path.write_text(original)
    assert poll(w) == []
    with db.connect() as conn:
        links.clear_parent(conn, child)
    path.write_text(original.replace("working", "done"))
    assert poll(w) == []
    link(child, parent)
    assert "Status: working -> done" in poll(w)[0]
    with db.connect() as conn:
        links.clear_parent(conn, child)
    assert poll(w) == []
    link(child, parent)
    assert poll(w) == []


def test_independent_watchers_keep_their_own_baselines(family):
    _, _, path, _ = family
    first, second = open_watch(family), open_watch(family, me="second")
    path.write_text(path.read_text().replace("working", "done"))
    assert poll(first)
    assert poll(second)
    assert poll(open_watch(family)) == []
    assert poll(open_watch(family, me="second")) == []


def test_failed_delivery_is_retried_on_rearm(family):
    _, _, path, _ = family
    w = open_watch(family)
    path.write_text(path.read_text().replace("working", "done"))

    def fail(message):
        raise delivery.Failed("queue failed")

    with pytest.raises(delivery.Failed):
        briefs_events.poll(w, fail)
    assert poll(open_watch(family))
    assert poll(open_watch(family)) == []


def test_quiet_window_ignores_unrelated_progress_and_batches_children(family, monkeypatch):
    parent, _, path, _ = family
    other, other_path = lemon("other")
    link(other, parent)
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    w = open_watch(family, quiet=2)
    path.write_text(path.read_text().replace("working", "merge"))
    assert poll(w) == []
    clock[0] = 1
    other_path.write_text(other_path.read_text().replace("working", "done"))
    assert poll(w) == []
    clock[0] = 2
    path.write_text(path.read_text() + "\n### Next\n\n- progress\n")
    assert poll(w) == []
    clock[0] = 3
    [event] = poll(w)
    assert "Status: working -> merge" in event
    assert f"{other}: Status: working -> done" in event
