from pathlib import Path

from lemonaid.doc_plugins import document

from .shared import RELAY, fake

_PATH = Path("/notes/review.md")
_TEXT = 'Intro {==x==}{{author="Sam">>relay ask<<}}\n%% Ana: fake ask\n%% Me (Author): mine\nEnd\n'


def test_each_plugin_removes_its_comments_from_what_the_one_before_left():
    assert document.body([fake(), RELAY], _PATH, _TEXT) == "Intro x\nEnd\n"


def test_no_plugins_leave_the_text_as_it_is():
    assert document.body([], _PATH, _TEXT) == _TEXT


def test_a_failed_plugin_gives_no_body(capfd):
    assert document.body([RELAY, fake("--fail")], _PATH, _TEXT) is None
    assert "fake plugin failed on purpose" in capfd.readouterr().err


def test_every_plugin_reads_the_same_text_for_threads():
    readings = document.threads([fake(), RELAY], _PATH, _TEXT, {"Me (Author)"})

    assert [(r.plugin, [(t.last, t.waiting) for t in r.reading.threads]) for r in readings] == [
        ("fake", [("Ana", True), ("Me (Author)", False)]),
        ("relay-comments", [("Sam", True)]),
    ]


def test_a_failed_plugin_reads_as_incomplete():
    [reading] = document.threads([fake("--fail")], _PATH, _TEXT, ())

    assert reading.reading.threads == () and not reading.reading.complete


def test_last_authors_come_from_every_plugin():
    assert document.last_authors([fake(), RELAY], _PATH, _TEXT) == {"Ana", "Me (Author)", "Sam"}
