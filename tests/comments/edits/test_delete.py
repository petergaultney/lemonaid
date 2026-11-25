import pytest

from lemonaid.comments import edits, parse


def _two_threads() -> str:
    text = "x = 1\ny = 2\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 0, 5, author="Sam", body="q", comment_id="Root").edits,
    )
    at = text.index("y = 2")
    text = edits.apply(
        text,
        edits.add_comment(
            text, "python", at, at + 5, author="Sam", body="q2", comment_id="Other"
        ).edits,
    )
    text = edits.apply(
        text,
        edits.reply(text, "python", "Root", author="Lemon", body="a", comment_id="Answer").edits,
    )
    text = edits.apply(
        text,
        edits.reply(text, "python", "Answer", author="Sam", body="b", comment_id="Again").edits,
    )
    return edits.apply(text, [edits.resolve(text, "python", "Again", author="Sam")])


def test_deleting_a_first_comment_removes_its_thread_and_markers() -> None:
    text = _two_threads()

    result = edits.apply(text, edits.delete(text, "python", "Root"))

    doc = parse.parse(result, "python")
    assert [c.id for c in doc.comments] == ["Other"]
    assert doc.resolutions == ()
    assert {m.id for m in doc.markers} == {"Other"}
    assert not doc.errors


def test_deleting_a_reply_removes_it_and_its_replies_and_leaves_the_rest() -> None:
    text = _two_threads()

    result = edits.apply(text, edits.delete(text, "python", "Answer"))

    doc = parse.parse(result, "python")
    assert [c.id for c in doc.comments] == ["Root", "Other"]
    assert doc.resolutions == ()
    assert {m.id for m in doc.markers} == {"Root", "Other"}


def test_deleting_the_last_comment_gives_back_the_file_without_comments() -> None:
    text = "x = 1\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 0, 5, author="Sam", body="q", comment_id="Root").edits,
    )

    result = edits.apply(text, edits.delete(text, "python", "Root"))

    assert result == "x = 1\n"


def test_deleting_a_comment_that_is_not_there_is_refused() -> None:
    with pytest.raises(ValueError, match="no comment Nope"):
        edits.delete(_two_threads(), "python", "Nope")


def test_deleting_the_last_comment_leaves_the_rest_of_the_text_untouched() -> None:
    text = "x = 1\ny = 2\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 6, 11, author="Sam", body="q", comment_id="Root").edits,
    )

    planned = edits.delete(text, "python", "Root")

    assert edits.apply(text, planned) == "x = 1\ny = 2\n"
    assert all(e.start > 0 for e in planned)


def test_deleting_the_last_comment_refuses_a_section_with_a_line_it_cannot_read() -> None:
    text = "x = 1\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 0, 5, author="Sam", body="q", comment_id="Root").edits,
    )
    text += "# not a record\n"

    with pytest.raises(ValueError, match="isn't a record"):
        edits.delete(text, "python", "Root")


def test_deleting_a_thread_with_a_second_opening_marker_is_refused() -> None:
    text = _two_threads()
    text = text.replace("x = 1\n", "x = 1\n# [lma:Root]\n", 1)

    with pytest.raises(ValueError, match="more than one opening"):
        edits.delete(text, "python", "Root")
