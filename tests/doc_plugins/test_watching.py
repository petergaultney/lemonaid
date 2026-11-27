"""`watch doc` with a plugin it knows nothing about: the contract a comment format relies on."""

import json

import pytest

from lemonaid.doc_plugins import document
from lemonaid.plugins import processes
from lemonaid.watch import doc_events, own_edits

from .shared import RELAY, fake

_ME = "Me (Author)"


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Notes\n\nA claim.\n")
    return path


def _watch(tmp_path, doc, plugins, edits=False):
    return doc_events.open_watch(
        tmp_path / "state", doc, _ME, [], edits=edits, quiet=0, plugins=plugins
    )


def _poll(w) -> list[str]:
    sent: list[str] = []
    doc_events.poll(w, lambda message: sent.append(message) or True)
    return sent


def _add(doc, line: str) -> None:
    doc.write_text(doc.read_text() + line)


def test_a_waiting_thread_wakes_the_reader_once(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake()])
    _add(doc, "%% Ana: is this right?\n")

    [message] = _poll(w)
    assert "1 new or changed unanswered thread(s)" in message
    assert "Ana: is this right?" in message
    assert _poll(w) == []


def test_a_thread_the_reader_wrote_last_does_not_wake_it(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake()])
    _add(doc, f"%% {_ME}: noted\n")

    assert _poll(w) == []


def test_adding_a_comment_is_not_a_body_edit_and_editing_around_it_is(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake()], edits=True)
    _add(doc, f"%% {_ME}: my note\n")
    assert _poll(w) + _poll(w) == []

    _add(doc, "New prose.\n")
    _poll(w)
    [message] = _poll(w)
    assert "+ New prose." in message and "my note" not in message


def test_two_plugins_in_one_doc_each_report_their_own_threads(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake(), RELAY], edits=True)
    _add(doc, '%% Ana: fake ask\nSee {{author="Sam">>relay ask<<}}\n')

    [message] = _poll(w)
    assert "2 new or changed unanswered thread(s)" in message
    assert "Ana: fake ask" in message and "Sam:\nrelay ask" in message
    _poll(w)
    assert _poll(w) == []  # the body edit is "See " only, then quiet


def test_a_plugins_notes_come_ahead_of_its_new_threads(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake("--note", "Answer with: fake reply <id>")])
    _add(doc, "%% Ana: ask\n")

    [message] = _poll(w)
    assert message.index("Answer with: fake reply <id>") < message.index("Ana: ask")


def test_a_failed_plugin_neither_wakes_nor_forgets_what_it_reported(tmp_path, doc, capfd):
    w = _watch(tmp_path, doc, [fake()], edits=True)
    _add(doc, "%% Ana: ask\n")
    assert len(_poll(w)) == 1

    w.plugins = [fake("--fail")]
    assert _poll(w) + _poll(w) == []  # no thread, and no body edit with the comment in it
    assert "failed on purpose" in capfd.readouterr().err

    w.plugins = [fake()]
    assert _poll(w) == []


@pytest.mark.parametrize("flag", ["--incomplete", "--fail"])
def test_an_incomplete_reading_keeps_the_threads_already_reported(tmp_path, doc, flag):
    w = _watch(tmp_path, doc, [fake()])
    _add(doc, "%% Ana: first\n")
    _poll(w)
    w.plugins = [fake(flag)]
    doc.write_text("# Notes\n")
    _poll(w)

    w.plugins = [fake()]
    _add(doc, "%% Ana: first\n")
    assert _poll(w) == []


def test_a_complete_reading_forgets_an_answered_thread_so_it_can_wake_again(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake()])
    _add(doc, "%% Ana: first\n")
    _poll(w)
    doc.write_text("# Notes\n")
    _poll(w)

    _add(doc, "%% Ana: first\n")
    assert len(_poll(w)) == 1


def test_threads_reported_before_plugins_existed_are_not_reported_again(tmp_path, doc):
    ask = '{{authorId="1" author="Sam">>is this true?<<}}'
    _add(doc, ask)
    w = _watch(tmp_path, doc, [RELAY])
    [[thread]] = [r.reading.threads for r in document.threads([RELAY], doc, doc.read_text(), ())]
    key = thread.key
    w.reported_path.write_text(json.dumps([key]))  # how a waiter saved it before plugins

    assert _poll(_watch(tmp_path, doc, [RELAY])) == []
    assert json.loads(w.reported_path.read_text()) == {"relay-comments": [key]}


def test_own_edits_are_recorded_on_the_body_without_comments(tmp_path, doc):
    root, writer, key = tmp_path / "own", "claude-s", "cli-1"
    own_edits.before_edit(root, writer, key, doc, [fake()])
    _add(doc, "%% Ana: a comment, which is not a body edit\n")

    assert own_edits.after_edit(root, writer, key, doc, [fake()])
    assert own_edits.transitions(root, writer, doc) == []


def test_no_own_edit_is_recorded_while_a_plugin_fails(tmp_path, doc):
    root, writer, key = tmp_path / "own", "claude-s", "cli-1"
    own_edits.before_edit(root, writer, key, doc, [fake("--fail")])
    _add(doc, "More.\n")

    assert not own_edits.after_edit(root, writer, key, doc, [fake()])


def test_a_watcher_started_while_a_plugin_fails_takes_its_baseline_once_it_recovers(tmp_path, doc):
    _add(doc, f"%% {_ME}: my note\n")
    w = _watch(tmp_path, doc, [fake("--fail")], edits=True)
    w.plugins = [fake()]
    assert _poll(w) + _poll(w) == []  # the comment is not a removed body line

    _add(doc, "New prose.\n")
    _poll(w)
    [message] = _poll(w)
    assert "+1/-0 lines" in message and "+ New prose." in message


def test_a_failed_before_edit_drops_an_earlier_one_with_the_same_key(tmp_path, doc):
    """Else that earlier digest pairs with this edit, and a human's change in between is lost."""
    root, writer, key = tmp_path / "own", "claude-s", "cli-1"
    own_edits.before_edit(root, writer, key, doc, [fake()])  # abandoned: no after_edit
    _add(doc, "A human's line.\n")
    own_edits.before_edit(root, writer, key, doc, [fake("--fail")])
    _add(doc, "The lemon's line.\n")

    assert not own_edits.after_edit(root, writer, key, doc, [fake()])
    assert own_edits.transitions(root, writer, doc) == []


def test_one_plugin_process_serves_every_call(tmp_path, doc):
    w = _watch(tmp_path, doc, [fake()], edits=True)
    for n in range(3):
        _add(doc, f"%% Ana: ask {n}\n")
        _poll(w)

    assert len(processes._running) == 1


def test_a_plugin_that_crashes_is_started_again_after_a_pause(tmp_path, doc, monkeypatch, capfd):
    w = _watch(tmp_path, doc, [fake("--crash")])
    _add(doc, "%% Ana: ask\n")
    assert _poll(w) == []
    assert "exited" in capfd.readouterr().err

    _add(doc, "%% Ana: again\n")
    assert _poll(w) == []
    assert capfd.readouterr().err == ""  # held off, and said once

    monkeypatch.setattr(processes, "RETRY_AFTER", 0.0)
    _add(doc, "%% Ana: and again\n")
    assert _poll(w) == []
    assert "exited" in capfd.readouterr().err  # started, and crashed, again
