import pytest

from lemonaid.comments import edits, model, parse, threads

_AT = "2026-11-19T19:40:00Z"


def test_a_resolution_is_appended_and_resolves_its_branch() -> None:
    text = "a = 1\n"
    added = edits.add_comment(text, "python", 0, 0, author="a", body="b", at=_AT, comment_id="Root")
    text = edits.apply(text, added.edits)

    result = edits.resolve(text, "python", "Root", author="caleb.gregory", at=_AT)

    doc = parse.parse(edits.apply(text, [result]), "python")
    assert doc.resolutions == (
        model.Resolution(resolves="Root", author="caleb.gregory", at=_AT, offset=len(text)),
    )
    assert threads.threads(doc)[0].root.resolved is True


def test_resolving_a_comment_that_isn_t_there_is_refused() -> None:
    with pytest.raises(ValueError, match="no comment Gone"):
        edits.resolve("a = 1\n", "python", "Gone", author="a")
