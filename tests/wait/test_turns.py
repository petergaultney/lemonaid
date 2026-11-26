"""A batch waits while its lemon is mid-turn, and a body change made during the turn is its own."""

import time

from lemonaid.messages import store
from lemonaid.watch import scout_pollers, turns

from . import shared


def test_mail_waits_out_the_turn_and_arrives_in_one_batch(tmp_path):
    turn = [turns.Turn(True, time.time(), 0)]
    sent = []
    _path, inbox, _root, stop, thread, errors = shared.start(
        tmp_path, shared.BRIEF, sent.append, latest_turn=lambda: turn[0]
    )
    try:
        store.send(inbox, "first", "other.IndexElf")
        time.sleep(0.2)
        store.send(inbox, "second", "other.IndexElf")
        time.sleep(0.2)
        assert sent == []
        turn[0] = turns.Turn(False, turn[0].started, time.time())
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "first" in sent[0] and "second" in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_a_body_change_made_during_the_turn_wakes_nobody_and_a_later_comment_does(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(scout_pollers, "_THREAD_SETTLE", 0.1)
    doc = tmp_path / "draft.md"
    doc.write_text("body\n")
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet .02 --interval .01`\n"
    turn = [turns.Turn(False, 0, 0)]
    sent = []
    _path, _inbox, root, stop, thread, errors = shared.start(
        tmp_path, text, sent.append, latest_turn=lambda: turn[0], writer="openclaw-agent:main:x"
    )
    try:
        shared.eventually(lambda: (root / "doc").exists())
        time.sleep(0.3)  # the scout sees the body before the turn
        turn[0] = turns.Turn(True, time.time(), 0)
        doc.write_text("body\n\nThe lemon's own paragraph.\n")
        time.sleep(0.5)  # past the scout's settle, so the change is seen while running
        turn[0] = turns.Turn(False, turn[0].started, time.time())
        time.sleep(0.5)
        assert sent == []
        doc.write_text(doc.read_text() + '\n{{authorId="human" author="Human">>why?<<}}\n')
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "why?" in sent[0] and "own paragraph" not in sent[0]
    finally:
        stop.set()
        thread.join(5)


def test_a_body_edit_made_before_the_turn_is_still_reported_after_it(tmp_path, monkeypatch):
    monkeypatch.setattr(scout_pollers, "_THREAD_SETTLE", 0.1)
    doc = tmp_path / "draft.md"
    doc.write_text("body\n")
    text = shared.BRIEF + f"- `lemonaid watch doc --wait {doc} --quiet 1 --interval .01`\n"
    turn = [turns.Turn(False, 0, 0)]
    sent = []
    _path, _inbox, root, stop, thread, errors = shared.start(
        tmp_path, text, sent.append, latest_turn=lambda: turn[0], writer="openclaw-agent:main:x"
    )
    try:
        shared.eventually(lambda: (root / "doc").exists())
        time.sleep(0.3)
        doc.write_text("body\n\nA human's instruction.\n")
        time.sleep(0.3)  # seen, but not yet quiet for long enough to report
        turn[0] = turns.Turn(True, time.time(), 0)
        doc.write_text(doc.read_text() + '\n{{authorId="x" author="Author (IndexElf)">>noted<<}}\n')
        time.sleep(0.3)
        turn[0] = turns.Turn(False, turn[0].started, time.time())
        thread.join(5)
        assert not thread.is_alive() and not errors
        assert len(sent) == 1 and "A human's instruction." in sent[0]
    finally:
        stop.set()
        thread.join(5)
