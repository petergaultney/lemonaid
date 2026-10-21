import pytest

from lemonaid.brief import lemon_table
from lemonaid.watch import briefs_events, briefs_orphans, notes

from .shared import lemon, link, poll

_NOTES = {
    "child.done": "Toss its place.",
    "child.needs": "Answer it.",
    "watched.done": "Not yours to toss.",
    "orphan.done": "Adopt or toss.",
}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(briefs_orphans, "live_sessions", lambda socket: frozenset({"s-parent"}))


def _set(path, state):
    path.write_text(path.read_text().replace("Status: working", f"Status: {state}"))


def test_a_child_going_done_carries_the_child_done_note(family):
    parent, child, path, state_dir = family
    w = briefs_events.open_watch(state_dir, parent, "me", 0, notes=lambda: _NOTES)
    _set(path, "done")
    assert poll(w) == [
        f"{child}: Status: none -> done ({path})\n"
        "Your notes for these events:\n- child.done: Toss its place."
    ]


def test_without_a_note_for_its_kind_the_event_is_unchanged(family):
    parent, child, path, state_dir = family
    w = briefs_events.open_watch(state_dir, parent, "me", 0, notes=lambda: {"child.blocked": "x"})
    _set(path, "merge")
    assert poll(w) == [f"{child}: Status: none -> merge ({path})"]


def test_two_children_done_together_share_one_note(family):
    parent, _, path, state_dir = family
    second, second_path = lemon("second", channel="codex:second")
    link(second, parent)
    w = briefs_events.open_watch(state_dir, parent, "me", 0, notes=lambda: _NOTES)
    _set(path, "done")
    _set(second_path, "done")
    [message] = poll(w)
    assert message.count("child.done") == 1


def test_a_new_needs_ask_carries_the_needs_note(family):
    parent, _, path, state_dir = family
    w = briefs_events.open_watch(state_dir, parent, "me", 0, needs=True, notes=lambda: _NOTES)
    path.write_text(path.read_text() + "- Pick a name\n")
    [message] = poll(w)
    assert message.endswith("- child.needs: Answer it.")


def test_a_listed_lemon_that_is_not_a_child_gets_the_watched_note(family):
    parent, _, _, state_dir = family
    other, other_path = lemon("other", channel="codex:other")
    w = briefs_events.open_watch(
        state_dir, parent, "me", 0, rows=(lemon_table.Row(other),), notes=lambda: _NOTES
    )
    _set(other_path, "done")
    [message] = poll(w)
    assert "watched.done: Not yours to toss." in message and "child.done" not in message


def test_an_orphan_gets_the_orphan_note(live, tmp_path):
    hq, _ = lemon("hq", channel="codex:hq", session="s-parent")
    _, path = lemon("stray", channel="codex:stray")
    w = briefs_events.open_watch(
        tmp_path / "state", hq, "me", 0, frozenset({"done"}), orphans=True, notes=lambda: _NOTES
    )
    _set(path, "done")
    [message] = poll(w)
    assert message.endswith("- orphan.done: Adopt or toss.")


def test_a_note_edited_after_the_watch_opens_reaches_the_next_report(family, tmp_path):
    parent, _, path, state_dir = family
    directory = tmp_path / "event-notes"
    directory.mkdir()
    (directory / "child.done.md").write_text("Old.")
    w = briefs_events.open_watch(
        state_dir, parent, "me", 0, notes=notes.reader(directory, "claude")
    )
    (directory / "child.done.md").write_text("New.")
    _set(path, "done")
    [message] = poll(w)
    assert message.endswith("- child.done: New.")
