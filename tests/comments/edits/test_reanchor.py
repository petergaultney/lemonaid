import pytest

from lemonaid.comments import edits, parse


@pytest.mark.parametrize(
    "kind,text,target,anchored",
    [
        (
            "markdown",
            "# R\n\nThe pre-commit hook is missing.\n",
            "pre-commit hook",
            "pre-commit hook",
        ),
        ("python", "x = 1\ny = 2\nz = 3\n", "z = 3", "z = 3\n"),
    ],
)
def test_a_thread_moves_to_the_new_range_and_its_old_markers_go(
    kind, text, target, anchored
) -> None:
    first_line = len(text.splitlines()[0])
    text = edits.apply(
        text,
        edits.add_comment(
            text, kind, 0, first_line, author="Sam", body="q", comment_id="Root"
        ).edits,
    )
    at = text.index(target)

    result = edits.apply(text, edits.reanchor(text, kind, "Root", at, at + len(target)))

    doc = parse.parse(result, kind)
    anchor = doc.anchor("Root")
    assert result[anchor.start : anchor.end] == anchored
    assert len([m for m in doc.markers if m.id == "Root"]) == 2
    assert not doc.errors


def test_a_reply_is_not_a_thread_to_move() -> None:
    text = "x = 1\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 0, 5, author="Sam", body="q", comment_id="Root").edits,
    )
    text = edits.apply(
        text, edits.reply(text, "python", "Root", author="A", body="a", comment_id="Ans").edits
    )

    with pytest.raises(ValueError, match="no thread Ans"):
        edits.reanchor(text, "python", "Ans", 0, 0)


def test_a_thread_can_grow_over_its_own_hidden_markers() -> None:
    text = "x = 1\ny = 2\nz = 3\n"
    at = text.index("y = 2")
    text = edits.apply(
        text,
        edits.add_comment(
            text, "python", at, at + 5, author="Sam", body="q", comment_id="Root"
        ).edits,
    )

    result = edits.apply(
        text, edits.reanchor(text, "python", "Root", 0, len(text.split("\n\n#")[0]))
    )

    doc = parse.parse(result, "python")
    anchor = doc.anchor("Root")
    assert result[anchor.start : anchor.end] == "x = 1\ny = 2\nz = 3\n"
    assert not doc.errors


def test_moving_a_thread_with_a_second_opening_marker_is_refused() -> None:
    text = "x = 1\ny = 2\nz = 3\n"
    text = edits.apply(
        text,
        edits.add_comment(text, "python", 0, 5, author="Sam", body="q", comment_id="Root").edits,
    )
    text = text.replace("y = 2\n", "y = 2\n# [lma:Root]\n", 1)
    at = text.index("z = 3")

    with pytest.raises(ValueError, match="more than one opening"):
        edits.reanchor(text, "python", "Root", at, at + 5)
