import pytest

from lemonaid.brief import store
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.watch import briefs_events, delivery

from .shared import lemon, link, open_watch, poll


@pytest.mark.parametrize("before", store.STATES)
@pytest.mark.parametrize("state", store.STATES)
def test_default_only_wakes_on_entry_to_merge_or_done(family, before, state):
    _, child, path, _ = family
    path.write_text(path.read_text().replace("Status: working", f"Status: {before}"))
    w = open_watch(family)
    path.write_text(path.read_text().replace(f"Status: {before}", f"Status: {state}"))
    expected = (
        [f"{child}: Status: {before} -> {state} ({path})"]
        if state in {"merge", "done"} and state != before
        else []
    )
    assert poll(w) == expected
    assert poll(w) == []
    assert poll(open_watch(family)) == []


@pytest.mark.parametrize("state", ["working", "merge", "done"])
def test_needs_and_progress_changes_stay_quiet(family, state):
    _, _, path, _ = family
    path.write_text(path.read_text().replace("Status: working", f"Status: {state}"))
    w = open_watch(family)
    for ask in ("pick a colour", "try the build", "nothing"):
        path.write_text(
            f"# child\n\nStatus: {state}\n\n## Now\n\n### Needs Peter\n\n- {ask}\n\n### Next\n\n- progress\n"
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


def test_new_children_are_filtered_and_nonchildren_and_grandchildren_ignored(family):
    parent, child, _, _ = family
    unrelated, unrelated_path = lemon("unrelated")
    grandchild, grandchild_path = lemon("grandchild")
    link(grandchild, child)
    w = open_watch(family)
    unrelated_path.write_text(unrelated_path.read_text().replace("working", "merge"))
    grandchild_path.write_text(grandchild_path.read_text().replace("working", "done"))
    assert poll(w) == []
    new, new_path = lemon("new", "waiting")
    link(new, parent)
    assert poll(w) == []
    new_path.write_text(new_path.read_text().replace("Status: waiting", "Status: done"))
    assert poll(w) == [f"{new}: Status: waiting -> done ({new_path})"]
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


def test_quiet_window_ignores_progress_and_batches_children(family, monkeypatch):
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


def test_filtered_sequence_reports_latest_previous_status_without_rearm(family):
    _, child, path, _ = family
    w = open_watch(family)
    before = "working"
    for state in ("waiting", "running", "blocked", "alert", "review", "approve", "running"):
        path.write_text(path.read_text().replace(f"Status: {before}", f"Status: {state}"))
        assert poll(w) == []
        before = state
    path.write_text(path.read_text().replace("Status: running", "Status: merge"))
    assert poll(w) == [f"{child}: Status: running -> merge ({path})"]


def test_filtered_state_is_saved_even_when_other_child_delivery_fails(family):
    parent, _, path, _ = family
    other, other_path = lemon("other")
    link(other, parent)
    w = open_watch(family)
    path.write_text(path.read_text().replace("Status: working", "Status: blocked"))
    other_path.write_text(other_path.read_text().replace("Status: working", "Status: merge"))

    def fail(message):
        raise delivery.Failed("queue failed")

    with pytest.raises(delivery.Failed):
        briefs_events.poll(w, fail)
    assert poll(open_watch(family)) == [f"{other}: Status: working -> merge ({other_path})"]
    path.write_text(path.read_text().replace("Status: blocked", "Status: done"))
    assert "Status: blocked -> done" in poll(open_watch(family))[0]


def test_ignored_changes_do_not_postpone_pending_selected_event(family, monkeypatch):
    parent, _, path, _ = family
    other, other_path = lemon("other")
    link(other, parent)
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    w = open_watch(family, quiet=2)
    path.write_text(path.read_text().replace("working", "merge"))
    assert poll(w) == []
    clock[0] = 1
    other_path.write_text(
        other_path.read_text().replace("working", "waiting") + "- decide a colour\n"
    )
    assert poll(w) == []
    clock[0] = 2
    assert "Status: working -> merge" in poll(w)[0]


@pytest.mark.parametrize("rearm", [False, True])
def test_pending_needs_edits_do_not_delay_delivery_or_failed_delivery_retry(
    family, monkeypatch, rearm
):
    _, child, path, _ = family
    clock = [0.0]
    monkeypatch.setattr(briefs_events.time, "monotonic", lambda: clock[0])
    w = open_watch(family, quiet=2)
    path.write_text(path.read_text().replace("Status: working", "Status: merge") + "- first ask\n")
    assert poll(w) == []
    clock[0] = 1
    path.write_text(path.read_text().replace("first ask", "second ask"))
    assert poll(w) == []
    clock[0] = 2

    def fail(message):
        assert message == f"{child}: Status: working -> merge; Needs: second ask ({path})"
        raise delivery.Failed("queue failed")

    with pytest.raises(delivery.Failed):
        briefs_events.poll(w, fail)
    if rearm:
        w = open_watch(family, quiet=2)
    clock[0] = 3
    path.write_text(path.read_text().replace("second ask", "latest ask"))
    if rearm:
        assert poll(w) == []
        clock[0] = 4
    assert poll(w) == [f"{child}: Status: working -> merge; Needs: latest ask ({path})"]
    assert poll(open_watch(family)) == []
