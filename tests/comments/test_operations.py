import pytest

from lemonaid.comments import edits, operations


@pytest.mark.parametrize(
    ("text", "lines", "selected"),
    [
        ("a\n\nb\n", "2", ""),
        ("a\nbc\n", "2", "bc"),
        ("a\r\nbc\r\n", "1-2", "a\r\nbc"),
        ("a\nbc", "2", "bc"),
        ("a\r\n", "1", "a"),
    ],
)
def test_lines_select_whole_lines_without_their_last_line_ending(text, lines, selected) -> None:
    start, end = operations.line_range(text, lines)

    assert text[start:end] == selected


@pytest.mark.parametrize(
    ("text", "lines"), [("a\n", "2"), ("a\r\n", "2"), ("", "1"), ("a\nb", "2-1")]
)
def test_lines_past_the_last_line_are_refused(text, lines) -> None:
    with pytest.raises(ValueError):
        operations.line_range(text, lines)


_FILE = (
    "x = 1\n"
    "\n"
    "# [lma:threads]\n"
    '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}\n'
)


@pytest.mark.parametrize(
    "operation",
    [
        operations.Add("1", "BraveFig (Author)", "a note"),
        operations.Reply("SleepRib", "BraveFig (Author)", "because"),
        operations.Resolve("SleepRib", "BraveFig (Author)"),
        operations.Strip(),
    ],
)
def test_an_operation_survives_its_json(operation) -> None:
    assert operations.from_json(operations.to_json(operation)) == operation


@pytest.mark.parametrize(
    "data",
    [{"op": "reply", "re": "SleepRib"}, {"op": "drop"}, {"op": "resolve", "id": 1, "author": "x"}],
)
def test_anything_else_is_not_an_operation(data) -> None:
    with pytest.raises(ValueError):
        operations.from_json(data)


@pytest.mark.parametrize(
    "operation",
    [
        operations.Add("1", "BraveFig (Author)", "a note"),
        operations.Reply("SleepRib", "BraveFig (Author)", "because"),
        operations.Resolve("SleepRib", "BraveFig (Author)"),
        operations.Strip(),
    ],
)
def test_an_operation_has_landed_once_its_edits_are_applied(operation) -> None:
    at = "2026-11-19T20:00:00Z"
    planned, comment_id = operations.edits_for(operation, _FILE, "python", at=at)
    applied = edits.apply(_FILE, planned)

    assert not operations.landed(operation, _FILE, "python", at=at, comment_id=comment_id)
    assert operations.landed(operation, applied, "python", at=at, comment_id=comment_id)


def test_the_same_reply_tried_again_with_its_id_is_refused_rather_than_written_twice() -> None:
    reply = operations.Reply("SleepRib", "BraveFig (Author)", "because")
    planned, comment_id = operations.edits_for(reply, _FILE, "python")

    with pytest.raises(ValueError):
        operations.edits_for(reply, edits.apply(_FILE, planned), "python", comment_id=comment_id)
