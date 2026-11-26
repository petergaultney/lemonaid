"""Event detection for one doc, and the state it keeps between waiters."""

import hashlib
import time

import pytest

from lemonaid.watch import delivery, doc_events, turns

_ASK = '{{authorId="1" author="Sam">>is this true?<<}}'
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


def test_state_files_keep_their_names(doc, state_dir):
    """Renaming them would make the next waiter for the same doc re-report what earlier ones did."""
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
    assert "Sam:\nis this true?" in sent[0]


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
    doc.write_text(doc.read_text() + '{{author="Sam">>also this<<}}')
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
    assert "line 4 [# Review]; 0 removed line(s)\n+ A new line." in sent[0]
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
    assert sent == [
        f"{doc} was created (+3/-0 lines), quiet for 0s\n"
        "lines 1-3 [# Review]; 0 removed line(s)\n+ # Review\n+ \n+ A claim."
    ]


def test_a_doc_created_while_no_waiter_ran_is_reported(tmp_path, state_dir):
    doc = tmp_path / "later.md"
    doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text("# Review\n")
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "was created" in sent[0]


def test_a_large_body_edit_is_cut_to_the_batch_limit(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc.write_text("\n".join(f"{i} " + "x" * 7990 for i in range(30)))
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert len(sent[0]) < 31000
    assert "characters omitted; read the source" in sent[0]


def test_a_comment_and_a_large_edit_each_keep_a_share_of_the_batch(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    big = "\n".join(f"{i} " + "x" * 7990 for i in range(30))
    doc.write_text(big)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc.write_text(big + _ASK)
    doc_events.poll(w, _collect(sent))

    assert len(sent[0]) < 31000
    assert "Sam:\nis this true?" in sent[0]
    assert "body of" in sent[0]


def test_two_new_threads_are_counted_as_two_events(doc, state_dir):
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=False, quiet=45)
    doc.write_text(doc.read_text() + _ASK + '\n\n{{authorId="2" author="Kit">>and this?<<}}')
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert (delivery.events_in(sent[0]), delivery.has_comments(sent[0])) == (2, True)


class _Clock:
    """The session's turns, set by each test as the lemon starts and ends them."""

    def __init__(self) -> None:
        self.turn = turns.Turn(False, 0, 0)

    def start(self) -> None:
        self.turn = turns.Turn(True, time.time(), 0)

    def end(self) -> None:
        self.turn = turns.Turn(False, self.turn.started, time.time())


def _openclaw_watch(state_dir, doc, tmp_path, clock):
    return doc_events.open_watch(
        state_dir,
        doc,
        _ME,
        [],
        edits=True,
        quiet=0,
        writer="openclaw-agent:main:x",
        own_root=tmp_path / "own",
        latest_turn=lambda: clock.turn,
    )


def _append(doc, line: str) -> None:
    doc.write_text(doc.read_text() + line)


def test_a_body_edit_seen_during_a_turn_is_the_lemons_own(doc, state_dir, tmp_path):
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    doc_events.poll(w, _collect(sent))
    clock.start()
    _append(doc, "The lemon's line.\n")
    doc_events.poll(w, _collect(sent))
    clock.end()

    for _ in range(3):
        assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    assert sent == [] and "The lemon's line." in w.settled_body


def test_someone_elses_edit_during_a_turn_also_counts_as_the_lemons(doc, state_dir, tmp_path):
    """The waiter can't tell who wrote a change it sees mid-turn; Claude Code's hooks have the
    same blind spot, but only for the length of one tool call."""
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    doc_events.poll(w, _collect(sent))
    clock.start()
    _append(doc, "A human's line, typed while the lemon worked.\n")
    doc_events.poll(w, _collect(sent))
    clock.end()

    for _ in range(3):
        doc_events.poll(w, _collect(sent))
    assert sent == []


def test_a_body_edit_seen_before_the_turn_is_reported_after_it(doc, state_dir, tmp_path):
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    doc_events.poll(w, _collect(sent))
    w.edits = False  # a scout reports body edits only after its quiet period
    _append(doc, "A human's line.\n")
    doc_events.poll(w, _collect(sent))
    clock.start()
    _append(doc, f"\n{_ASK.replace('Sam', 'Author (MotorHoe)')}\n")
    doc_events.poll(w, _collect(sent))
    clock.end()
    w.edits = True

    doc_events.poll(w, _collect(sent))  # just changed, as far as the body detector knows
    doc_events.poll(w, _collect(sent))

    assert len(sent) == 1 and "A human's line." in sent[0]


def test_an_own_edit_stays_its_own_after_a_later_turn(doc, state_dir, tmp_path):
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    w.edits = False
    doc_events.poll(w, _collect(sent))
    clock.start()
    _append(doc, "Written in the first turn.\n")
    doc_events.poll(w, _collect(sent))
    clock.end()
    time.sleep(0.01)
    clock.start()
    clock.end()
    w.edits = True

    for _ in range(2):
        assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    assert sent == []


def test_a_body_edit_made_after_the_turn_ended_is_reported(doc, state_dir, tmp_path):
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    doc_events.poll(w, _collect(sent))
    clock.start()
    clock.end()
    clock.turn = clock.turn._replace(started=clock.turn.started - 60, ended=clock.turn.ended - 60)
    _append(doc, "A human's line.\n")

    doc_events.poll(w, _collect(sent))

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "A human's line." in sent[0]


def test_a_body_edit_made_well_after_a_turn_is_reported(doc, state_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(turns, "SLACK", 0.05)
    clock = _Clock()
    w = _openclaw_watch(state_dir, doc, tmp_path, clock)
    sent: list[str] = []
    doc_events.poll(w, _collect(sent))
    clock.start()
    clock.end()
    time.sleep(0.1)
    doc_events.poll(w, _collect(sent))  # the body, unchanged, after the turn
    _append(doc, "A human's line.\n")

    doc_events.poll(w, _collect(sent))

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "A human's line." in sent[0]
