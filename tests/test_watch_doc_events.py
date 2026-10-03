"""Event detection for one doc, and the state it shares with the standalone watch-doc.py."""

import hashlib

import pytest

from lemonaid.watch import doc_events

_ASK = '{{authorId="1" author="Peter">>is this true?<<}}'
_ME = "Author (MotorHoe)"


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "review.md"
    path.write_text("# Review\n\nA claim.\n")
    return path


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "state"


def _collect(sent: list[str], ok: bool = True):
    def deliver(message: str) -> bool:
        sent.append(message)
        return ok

    return deliver


def test_state_files_are_named_like_the_standalone_waiters(doc, state_dir):
    """A lemonaid waiter and a watch-doc.py waiter for one (doc, me) share a lock and state."""
    expected = hashlib.sha1(f"{doc.resolve()}\0{_ME}".encode()).hexdigest()[:16]

    assert doc_events.state_stem(state_dir, doc, _ME) == state_dir / expected


def test_a_new_thread_is_delivered_once(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=False, quiet=45)
    doc.write_text(doc.read_text() + _ASK)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    assert len(sent) == 1
    assert "1 new or changed unanswered thread(s)" in sent[0]
    assert "Peter: is this true?" in sent[0]


def test_a_restarted_waiter_does_not_report_an_untouched_thread(doc, state_dir):
    doc.write_text(doc.read_text() + _ASK)
    doc_events.poll(doc_events.open_watch(state_dir, doc, _ME, [], False, 45), _collect([]))
    sent: list[str] = []

    restarted = doc_events.open_watch(state_dir, doc, _ME, [], False, 45)

    assert doc_events.poll(restarted, _collect(sent)) is doc_events.Outcome.NOTHING
    assert sent == []


def test_a_reported_thread_that_gains_a_block_is_reported_again(doc, state_dir):
    doc.write_text(doc.read_text() + _ASK)
    w = doc_events.open_watch(state_dir, doc, _ME, [], False, 45)
    doc_events.poll(w, _collect([]))
    doc.write_text(doc.read_text() + '{{author="Peter">>also this<<}}')
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "also this" in sent[0]


def test_a_failed_delivery_leaves_the_thread_unreported(doc, state_dir):
    doc.write_text(doc.read_text() + _ASK)
    w = doc_events.open_watch(state_dir, doc, _ME, [], False, 45)

    assert doc_events.poll(w, _collect([], ok=False)) is doc_events.Outcome.FAILED
    assert doc_events.poll(w, _collect([])) is doc_events.Outcome.DELIVERED


def test_a_body_edit_is_reported_once_it_has_been_quiet(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text(doc.read_text() + "A new line.\n")
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING  # just changed
    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "+1/-0 lines" in sent[0]
    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING


def test_an_edit_made_while_no_waiter_ran_is_reported(doc, state_dir):
    doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text(doc.read_text() + "Edited offline.\n")
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED


def test_adding_a_comment_is_not_a_body_edit(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text(doc.read_text() + '{{author="Author (MotorHoe)">>my own note<<}}')
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert sent == []


def test_a_doc_that_does_not_exist_yet_is_reported_when_it_is_created(tmp_path, state_dir):
    doc = tmp_path / "later.md"
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    doc.write_text("# Review\n\nA claim.\n")
    doc_events.poll(w, _collect(sent))  # just changed

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert sent == [f"{doc} was created (+3/-0 lines), quiet for 0s"]


def test_a_doc_created_while_no_waiter_ran_is_reported(tmp_path, state_dir):
    doc = tmp_path / "later.md"
    doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text("# Review\n")
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "was created" in sent[0]
