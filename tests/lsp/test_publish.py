from lsprotocol import types

from lemonaid.comments import parse
from lemonaid.lsp import positions, publish

_FILE = (
    "# [lma:SleepRib]\n"
    "x = 1\n"
    "# [/lma:SleepRib]\n"
    "\n"
    "# [lma:threads]\n"
    '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?\\nmore"}\n'
    '# {"id": "TinOwl", "re": "SleepRib", "author": "BraveFig (Author)", "at": "2026-11-19T19:41:00Z", "body": "because"}\n'
    '# {"id": "MossCap", "re": "TinOwl", "author": "Caleb Gregory", "at": "2026-11-19T19:42:00Z", "body": "ok"}\n'
    '# {"resolves": "MossCap", "author": "Caleb Gregory", "at": "2026-11-19T19:43:00Z"}\n'
)


def test_a_thread_comes_in_tree_order_with_each_comment_s_depth() -> None:
    doc = parse.parse(_FILE, "python")

    params = publish.threads_params("file:///x.py", 3, doc, positions.Codec(_FILE))

    [thread] = params["threads"]
    assert thread["anchor"] == {
        "start": {"line": 1, "character": 0},
        "end": {"line": 2, "character": 0},
    }
    assert [(c["id"], c["depth"], c["resolved"]) for c in thread["comments"]] == [
        ("SleepRib", 0, False),
        ("TinOwl", 1, False),
        ("MossCap", 2, True),
    ]


def test_a_hint_at_the_anchor_gives_the_first_line_and_the_reply_count() -> None:
    doc = parse.parse(_FILE, "python")

    [hint] = publish.diagnostics(doc, positions.Codec(_FILE))

    assert hint.message == "Caleb Gregory: why? (2 replies)"
    assert hint.severity == types.DiagnosticSeverity.Hint
    assert hint.range.start == types.Position(line=1, character=0)


def test_a_format_error_is_an_error_diagnostic() -> None:
    text = "x = 1\n\n# [lma:threads]\n# not json\n"
    doc = parse.parse(text, "python")

    [error] = publish.diagnostics(doc, positions.Codec(text))

    assert error.severity == types.DiagnosticSeverity.Error
    assert error.range.start.line == 3


def test_typing_above_the_section_or_moving_an_anchor_keeps_the_threads_key() -> None:
    moved = "# a new first line\n\n" + _FILE.replace("x = 1\n", "x = 1\ny = 2\n")

    assert publish.threads_key(parse.parse(moved, "python")) == publish.threads_key(
        parse.parse(_FILE, "python")
    )


def test_a_new_resolution_or_a_lost_anchor_changes_the_threads_key() -> None:
    resolved = (
        _FILE
        + '# {"resolves": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T20:00:00Z"}\n'
    )
    unanchored = _FILE.replace("# [lma:SleepRib]\n", "").replace("# [/lma:SleepRib]\n", "")
    key = publish.threads_key(parse.parse(_FILE, "python"))

    assert publish.threads_key(parse.parse(resolved, "python")) != key
    assert publish.threads_key(parse.parse(unanchored, "python")) != key
