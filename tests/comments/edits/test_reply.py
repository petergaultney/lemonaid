import pytest

from lemonaid.comments import edits, model, parse

_AT = "2026-11-19T19:40:00Z"
_LINE_SEPARATOR = chr(0x2028)


def _with_root(kind: model.FileKind, body: str = "why not yield_results here?") -> str:
    text = "a = 1\n" if kind == "python" else "Some prose.\n"
    added = edits.add_comment(
        text, kind, 0, 0, author="caleb.gregory", body=body, at=_AT, comment_id="Root"
    )
    return edits.apply(text, added.edits)


def test_a_reply_about_part_of_a_comment_records_its_span() -> None:
    text = _with_root("python")

    result = edits.reply(
        text,
        "python",
        "Root",
        author="Claude",
        body="it fails fast",
        span=(8, 20),
        at=_AT,
        comment_id="Reply",
    )

    assert edits.apply(text, result.edits).endswith(
        f'# {{"id": "Reply", "re": "Root", "span": [8, 20], "author": "Claude", "at": "{_AT}", '
        '"body": "it fails fast"}\n'
    )


@pytest.mark.parametrize("kind", ["python", "markdown"])
def test_any_body_reads_back_as_written(kind: model.FileKind) -> None:
    text = _with_root(kind)
    body = f"a --> b\nc{_LINE_SEPARATOR}d"

    result = edits.reply(text, kind, "Root", author="Claude", body=body, at=_AT)

    doc = parse.parse(edits.apply(text, result.edits), kind)
    assert ([c.body for c in doc.comments], doc.errors) == (
        ["why not yield_results here?", body],
        (),
    )


@pytest.mark.parametrize(
    "re_, span, message",
    [
        ("Gone", None, "no comment Gone"),
        ("Root", (0, 999), r"span \[0, 999\] is not in comment Root's body"),
    ],
)
def test_a_reply_to_something_that_isn_t_there_is_refused(
    re_: str, span: tuple[int, int] | None, message: str
) -> None:
    text = _with_root("python")

    with pytest.raises(ValueError, match=message):
        edits.reply(text, "python", re_, author="Claude", body="b", span=span)


def test_a_reply_can_t_reuse_an_id() -> None:
    text = _with_root("python")

    with pytest.raises(ValueError, match="already used"):
        edits.reply(text, "python", "Root", author="Claude", body="b", comment_id="Root")
