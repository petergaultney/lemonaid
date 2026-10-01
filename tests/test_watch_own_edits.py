"""A waiter is not woken by its own lemon's body edits, and is woken by everyone else's."""

import pytest

from lemonaid.claude import own_edit
from lemonaid.watch import doc_events, own_edits

_ME = "Author (MotorHoe)"
_SESSION = "11111111-2222-3333-4444-555555555555"
_ASK = '{{authorId="1" author="Peter">>is this true?<<}}'
_WRITER = own_edits.claude_writer(_SESSION)
_REPLY = '{{authorId="s" author="Author (MotorHoe)">>yes<<}}'


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("# Review\n\nA claim.\n")
    return path


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


def _watch(state_dir, doc, writer=_WRITER):
    return doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0, writer=writer)


def _hook_edit(state_dir, doc, new_text: str, tool_use_id: str = "toolu_1") -> None:
    """What Claude Code's Edit tool does with the own-edit hooks installed."""
    event = {
        "session_id": _SESSION,
        "tool_use_id": tool_use_id,
        "tool_input": {"file_path": str(doc)},
    }
    own_edit.record({**event, "hook_event_name": "PreToolUse"}, state_dir)
    doc.write_text(new_text)
    own_edit.record({**event, "hook_event_name": "PostToolUse"}, state_dir)


def _poll_twice(w) -> list[str]:
    """Two reads: the first sees a change, the second reports it once quiet (quiet=0)."""
    sent: list[str] = []

    def deliver(message: str) -> bool:
        sent.append(message)
        return True

    doc_events.poll(w, deliver)
    doc_events.poll(w, deliver)
    return sent


def test_an_own_edit_does_not_wake_the_waiter(doc, state_dir):
    w = _watch(state_dir, doc)
    _hook_edit(state_dir, doc, doc.read_text() + "Mine.\n")
    _hook_edit(state_dir, doc, doc.read_text() + "Mine again.\n", "toolu_2")

    assert _poll_twice(w) == []


def test_an_own_edit_made_between_waiters_does_not_wake_the_next(doc, state_dir):
    _watch(state_dir, doc)
    _hook_edit(state_dir, doc, doc.read_text() + "Mine.\n")

    assert _poll_twice(_watch(state_dir, doc)) == []


def test_an_edit_by_someone_else_before_mine_in_the_same_turn_still_wakes(doc, state_dir):
    w = _watch(state_dir, doc)
    doc.write_text(doc.read_text() + "Peter's.\n")
    _hook_edit(state_dir, doc, doc.read_text() + "Mine.\n")

    sent = _poll_twice(w)

    assert len(sent) == 1
    assert "+2/-0 lines" in sent[0]


def test_an_edit_by_someone_else_after_mine_wakes(doc, state_dir):
    w = _watch(state_dir, doc)
    _hook_edit(state_dir, doc, doc.read_text() + "Mine.\n")
    assert _poll_twice(w) == []

    doc.write_text(doc.read_text() + "Peter's.\n")

    assert len(_poll_twice(w)) == 1


def test_another_lemons_edit_wakes_this_one(doc, state_dir):
    """An author and its reviewer watch the same doc; each one's edits wake the other."""
    w = _watch(state_dir, doc, own_edits.claude_writer("reviewer-session"))
    _hook_edit(state_dir, doc, doc.read_text() + "The author's.\n")

    assert len(_poll_twice(w)) == 1


def test_an_own_reply_does_not_wake_and_anothers_new_comment_does(doc, state_dir):
    doc.write_text(doc.read_text() + f"{{==A claim.==}}{_ASK}\n")
    w = _watch(state_dir, doc)
    assert len(_poll_twice(w)) == 1  # Peter's question

    replied = doc.read_text().replace(_ASK, _ASK + _REPLY)
    _hook_edit(state_dir, doc, replied + "Mine.\n")
    assert _poll_twice(w) == []

    _hook_edit(state_dir, doc, doc.read_text() + "More of mine.\n", "toolu_2")
    doc.write_text(doc.read_text() + '{{authorId="2" author="Reviewer (SaltyEbb)">>and this?<<}}\n')
    sent = _poll_twice(w)

    assert len(sent) == 1
    assert "Reviewer (SaltyEbb): and this?" in sent[0]


def _cli_edit(state_dir, doc, writer: str, new_text: str) -> None:
    """`--editing`, an edit through a shell or Codex's apply_patch, then `--mine`."""
    own_edits.before_edit(state_dir, writer, own_edits.cli_key(doc), doc)
    doc.write_text(new_text)
    assert own_edits.after_edit(state_dir, writer, own_edits.cli_key(doc), doc)


def test_an_edit_recorded_with_editing_and_mine_does_not_wake(doc, state_dir):
    w = _watch(state_dir, doc, "codex-thread")
    _cli_edit(state_dir, doc, "codex-thread", doc.read_text() + "Mine, through the shell.\n")

    assert _poll_twice(w) == []


def test_an_edit_by_someone_else_before_editing_still_wakes(doc, state_dir):
    w = _watch(state_dir, doc, "codex-thread")
    doc.write_text(doc.read_text() + "Peter's.\n")
    _cli_edit(state_dir, doc, "codex-thread", doc.read_text() + "Mine.\n")

    assert len(_poll_twice(w)) == 1


def test_mine_without_editing_records_nothing(doc, state_dir):
    w = _watch(state_dir, doc, "codex-thread")
    doc.write_text(doc.read_text() + "Mine, unannounced.\n")

    assert not own_edits.after_edit(state_dir, "codex-thread", own_edits.cli_key(doc), doc)
    assert len(_poll_twice(w)) == 1


def test_an_old_transition_does_not_cover_a_later_outside_edit(doc, state_dir):
    """A -> B -> C -> B by the lemon, then Peter B -> C and the lemon C -> D: Peter's edit wakes."""
    a = doc.read_text()
    w = _watch(state_dir, doc)
    _hook_edit(state_dir, doc, a + "B\n", "t1")
    assert _poll_twice(w) == []
    _hook_edit(state_dir, doc, a + "B\nC\n", "t2")
    _hook_edit(state_dir, doc, a + "B\n", "t3")
    assert _poll_twice(w) == []

    doc.write_text(a + "B\nC\n")
    _hook_edit(state_dir, doc, a + "B\nC\nD\n", "t4")

    assert len(_poll_twice(w)) == 1


def test_an_outside_edit_matching_an_unread_own_transition_wakes(doc, state_dir):
    """The lemon goes B -> C -> B between two reads; Peter's later edit to C is not the lemon's."""
    w = _watch(state_dir, doc)
    b = doc.read_text()
    _hook_edit(state_dir, doc, b + "C\n", "t1")
    _hook_edit(state_dir, doc, b, "t2")
    doc.write_text(b + "C\n")

    assert len(_poll_twice(w)) == 1


def test_a_waiter_that_knows_no_writer_reports_every_edit(doc, state_dir):
    w = _watch(state_dir, doc, writer="")
    _hook_edit(state_dir, doc, doc.read_text() + "Mine.\n")

    assert len(_poll_twice(w)) == 1


def test_the_hook_ignores_docs_no_waiter_of_this_session_watches(doc, state_dir, tmp_path):
    _watch(state_dir, doc)
    other = tmp_path / "notes.md"
    other.write_text("x\n")
    _hook_edit(state_dir, other, "y\n")

    assert not (own_edits.writer_dir(state_dir, _WRITER) / "pending").exists()


def test_chain_to_needs_every_new_transition_in_order():
    assert own_edits.chain_to([(1, "a", "b"), (2, "b", "c")], 0, "a", "c") == 2
    assert own_edits.chain_to([(1, "a", "b"), (2, "x", "c")], 0, "a", "c") is None
    assert own_edits.chain_to([(1, "a", "b"), (2, "b", "a")], 0, "a", "b") is None
    assert own_edits.chain_to([(1, "z", "a"), (2, "a", "b")], 1, "a", "b") == 2
    assert own_edits.chain_to([], 0, "a", "a") is None
