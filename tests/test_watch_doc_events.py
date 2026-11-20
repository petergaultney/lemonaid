"""Event detection for one doc, and the state it keeps between waiters."""

import hashlib

import pytest

from lemonaid.comments import edits
from lemonaid.watch import delivery, doc_events

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


def _in_file_comment(path, *, author: str, comment_id: str, re_: str | None = None) -> None:
    text = path.read_text()
    kind = "python" if path.suffix == ".py" else "markdown"
    added = (
        edits.reply(
            text, kind, re_, author=author, body=f"{comment_id} says hi", comment_id=comment_id
        )
        if re_
        else edits.add_comment(
            text, kind, 0, 0, author=author, body=f"{comment_id} says hi", comment_id=comment_id
        )
    )
    path.write_text(edits.apply(text, added.edits))


@pytest.fixture
def code(tmp_path):
    path = tmp_path / "work.py"
    path.write_text("def f(x):\n    return x + 1\n")
    return path


def test_an_in_file_comment_is_delivered_once_with_how_to_answer_it(code, state_dir):
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    _in_file_comment(code, author="Sam", comment_id="Asked")
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    assert len(sent) == 1
    assert "1 new or changed unanswered comment(s)" in sent[0]
    assert "Sam [Asked, new thread]:\nAsked says hi" in sent[0]
    assert f"lemonaid comments reply {code} --re <id>" in sent[0]


def test_a_reply_signed_with_the_lemon_s_signature_answers_the_comment(code, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    _in_file_comment(code, author="Motor Hoe (Author)", comment_id="Answer", re_="Asked")
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING
    assert sent == []


def test_a_reply_to_the_lemon_wakes_it_again(code, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    _in_file_comment(code, author="MotorHoe (Author)", comment_id="Answer", re_="Asked")
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    doc_events.poll(w, _collect([]))
    _in_file_comment(code, author="Sam", comment_id="Again", re_="Answer")
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "Sam [Again, re Answer]" in sent[0]


def test_adding_an_in_file_comment_is_not_a_body_edit(code, state_dir):
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=True, quiet=0)
    _in_file_comment(code, author="MotorHoe (Author)", comment_id="Mine")
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert sent == []


def test_relay_blocks_in_a_file_with_a_threads_section_are_not_read(tmp_path, state_dir):
    doc = tmp_path / "review.md"
    doc.write_text("# Review\n")
    _in_file_comment(doc, author="MotorHoe (Author)", comment_id="Mine")
    doc.write_text(doc.read_text().replace("# Review\n", "# Review\n" + _ASK + "\n", 1))
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=False, quiet=45)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING


def test_the_first_in_file_comment_does_not_turn_relay_markup_into_a_body_edit(tmp_path, state_dir):
    doc = tmp_path / "review.md"
    doc.write_text("# Review\n\n{==line==}" + _ASK + "\n")
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=True, quiet=0)
    doc_events.poll(w, _collect([]))
    _in_file_comment(doc, author="MotorHoe (Author)", comment_id="Mine")
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert sent == []


def test_a_comment_added_when_strip_would_refuse_is_not_a_body_edit(code, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    code.write_text(
        code.read_text().replace("# [lma:Asked]\n", "# [lma:Asked]\n# [lma:Asked]\n", 1)
    )
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=True, quiet=0)
    doc_events.poll(w, _collect([]))
    text = code.read_text()
    added = edits.add_comment(
        text,
        "python",
        len("# [lma:Asked]\n" * 2),
        len("# [lma:Asked]\n" * 2),
        author="MotorHoe (Author)",
        body="mine",
        comment_id="Mine",
    )
    code.write_text(edits.apply(text, added.edits))
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert sent == []


def test_a_section_gone_for_one_poll_does_not_report_its_comments_again(code, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    commented = code.read_text()
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    doc_events.poll(w, _collect([]))
    code.write_text("def f(x):\n    return x + 1\n")
    doc_events.poll(w, _collect([]))
    code.write_text(commented)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING


def test_a_relay_thread_hidden_by_a_section_is_not_reported_again_when_it_goes(tmp_path, state_dir):
    doc = tmp_path / "review.md"
    doc.write_text("# Review\n\n" + _ASK + "\n")
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=False, quiet=45)
    doc_events.poll(w, _collect([]))
    relay_only = doc.read_text()
    _in_file_comment(doc, author="MotorHoe (Author)", comment_id="Mine")
    doc_events.poll(w, _collect([]))
    doc.write_text(relay_only)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.NOTHING


def test_an_answered_comment_that_waits_again_is_reported_again(code, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    asked_only = code.read_text()
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    doc_events.poll(w, _collect([]))
    _in_file_comment(code, author="MotorHoe (Author)", comment_id="Answer", re_="Asked")
    doc_events.poll(w, _collect([]))
    code.write_text(asked_only)  # someone deletes the answer's record by hand
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "Ids: Asked" in sent[0]


def test_the_watcher_reads_a_bare_cr_file_as_the_cli_does(tmp_path, state_dir):
    doc = tmp_path / "ghost.py"
    record = '# {"id": "Ghost", "author": "Sam", "at": "2026-11-19T19:40:00Z", "body": "boo"}'
    doc.write_bytes(f"x = 1\r# [lma:threads]\r{record}\r".encode())
    w = doc_events.open_watch(state_dir, doc, _ME, [], edits=False, quiet=45)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert not any("Ghost" in m for m in sent)


def test_a_long_wake_keeps_the_ids_and_how_to_answer(code, state_dir):
    for n in range(9):
        text = code.read_text()
        added = edits.add_comment(
            text, "python", 0, 0, author="Sam", body="x" * 4001, comment_id=f"Long{n}"
        )
        code.write_text(edits.apply(text, added.edits))
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))

    assert "Ids: Long" in sent[0] and "Long8" in sent[0]
    assert f"lemonaid comments reply {code} --re <id>" in sent[0]


def test_a_different_comment_that_reuses_an_id_is_reported(code, state_dir):
    original = code.read_text()
    _in_file_comment(code, author="Sam", comment_id="Reuse")
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=False, quiet=45)
    doc_events.poll(w, _collect([]))
    code.write_text(original)
    doc_events.poll(w, _collect([]))
    text = code.read_text()
    added = edits.add_comment(
        text, "python", 0, 0, author="Sam", body="a new question", comment_id="Reuse"
    )
    code.write_text(edits.apply(text, added.edits))
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "Ids: Reuse." in sent[0]


def test_editing_relay_shaped_text_in_python_code_is_a_body_edit(code, state_dir):
    code.write_text('EXAMPLE = """{{author="Sam">>hello<<}}"""\n')
    _in_file_comment(code, author="MotorHoe (Author)", comment_id="Mine")
    w = doc_events.open_watch(state_dir, code, _ME, [], edits=True, quiet=0)
    doc_events.poll(w, _collect([]))
    code.write_text(code.read_text().replace("hello", "goodbye"))
    sent: list[str] = []

    doc_events.poll(w, _collect(sent))
    doc_events.poll(w, _collect(sent))

    assert any("goodbye" in m for m in sent)


def test_a_link_with_another_extension_is_watched_as_the_file_it_names(code, tmp_path, state_dir):
    _in_file_comment(code, author="Sam", comment_id="Asked")
    alias = tmp_path / "alias.md"
    alias.symlink_to(code)
    w = doc_events.open_watch(state_dir, alias, _ME, [], edits=False, quiet=45)
    sent: list[str] = []

    assert doc_events.poll(w, _collect(sent)) is doc_events.Outcome.DELIVERED
    assert "Ids: Asked." in sent[0]
