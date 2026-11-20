import pytest

from lemonaid.comments import edits, model, parse

_AT = "2026-11-19T19:40:00Z"
_BACKTICK = chr(0x60)


@pytest.mark.parametrize(
    "kind, original, anchored",
    [
        ("python", "def f():\n    if x:\n        return 1\n    return 2\n", "return 1"),
        ("python", "x = 1\n", "x = 1\n"),
        ("python", "a = 1\r\nb = 2\r\n", "b = 2"),
        ("python", 'def f():\n    """One.\n\n    Two.\n    """\n', "Two"),
        ("markdown", "# Title\n\nWe drop the row here.\n", "drop the row"),
        ("markdown", "x\n", "x\n"),
        ("markdown", "x", "x"),
        ("markdown", "Use\r\nthis.\r\n", "this"),
        ("markdown", "Before.\n\n```py\nx = 1\n```\nAfter.\n", "x = 1"),
        ("markdown", f"Call {_BACKTICK}code{_BACKTICK} now.\n", "code"),
    ],
)
def test_stripping_every_comment_gives_back_the_original(
    kind: model.FileKind, original: str, anchored: str
) -> None:
    start = original.index(anchored)
    ranged = edits.add_comment(
        original, kind, start, start + len(anchored), author="a", body="one", at=_AT
    )
    commented = edits.apply(original, ranged.edits)
    point = edits.add_comment(commented, kind, 0, 0, author="a", body="two", at=_AT)
    commented = edits.apply(commented, point.edits)
    reply = edits.reply(commented, kind, ranged.comment_id, author="Claude", body="three", at=_AT)
    commented = edits.apply(commented, reply.edits)

    result = edits.strip(commented, kind)

    assert result == original


@pytest.mark.parametrize("kind", ["python", "markdown"])
def test_a_point_in_an_empty_file_strips_to_nothing(kind: model.FileKind) -> None:
    added = edits.add_comment("", kind, 0, 0, author="a", body="b", at=_AT)

    result = edits.strip(edits.apply("", added.edits), kind)

    assert result == ""


def test_a_marker_whose_pair_is_missing_is_stripped_too() -> None:
    record = '# {"id": "Root", "author": "a", "at": "2026-11-19T19:40:00Z", "body": "b"}'
    text = f"# [/lma:Root]\nx = 1\n\n# [lma:threads]\n{record}\n"

    result = edits.strip(text, "python")

    assert result == "x = 1\n"


def test_a_marker_with_no_comment_in_the_file_is_left_alone() -> None:
    text = "# [lma:Example]\nx = 1\n"

    result = edits.strip(text, "python")

    assert result == text


@pytest.mark.parametrize(
    "text",
    [
        ">     <!-- [lma:Example] -->\n>     verbatim\n",
        "- ~~~md\n  <!-- [lma:Example] -->\n  ~~~\n",
    ],
)
def test_examples_in_containers_our_masking_misreads_stay(text: str) -> None:
    result = edits.strip(text, "markdown")

    assert result == text


def test_a_threads_header_inside_a_string_is_left_alone() -> None:
    text = 'value = """\n# [lma:threads]\nkeep me\n"""\nprint(value)\n'

    result = edits.strip(text, "python")

    assert result == text


def test_text_after_a_markdown_threads_section_is_kept() -> None:
    added = edits.add_comment("x\n", "markdown", 0, 0, author="a", body="b", at=_AT)
    commented = edits.apply("x\n", added.edits) + "Keep me.\n"

    result = edits.strip(commented, "markdown")

    assert result == "x\nKeep me.\n"


def test_a_markdown_section_without_its_closing_is_refused() -> None:
    text = '<!-- [lma:K7] -->x\n\n<!-- [lma:threads]\n{"id": "K7"}\n'

    with pytest.raises(ValueError, match="no closing -->"):
        edits.strip(text, "markdown")


@pytest.mark.parametrize("kind", ["python", "markdown"])
def test_a_second_point_beside_the_first_still_strips_exactly(kind: model.FileKind) -> None:
    original = "" if kind == "markdown" else "x = 1\n"
    first = edits.add_comment(original, kind, 0, 0, author="a", body="one", at=_AT)
    commented = edits.apply(original, first.edits)
    second = edits.add_comment(commented, kind, 0, 0, author="a", body="two", at=_AT)
    commented = edits.apply(commented, second.edits)

    result = edits.strip(commented, kind)

    assert result == original


def test_a_point_at_the_end_of_a_python_range_strips_to_the_file_with_a_final_newline() -> None:
    ranged = edits.add_comment("x", "python", 0, 1, author="a", body="one", at=_AT)
    commented = edits.apply("x", ranged.edits)
    section = parse.parse(commented, "python").section
    assert section is not None
    point = edits.add_comment(
        commented, "python", section.start, section.start, author="a", body="two", at=_AT
    )
    commented = edits.apply(commented, point.edits)

    result = edits.strip(commented, "python")

    assert result == "x\n"


def test_markers_on_unicode_separated_lines_inside_a_string_stay() -> None:
    text = f'# has{chr(0x2028)}separator\nx = """\n    # [lma:Literal]\n"""\nprint(x)\n'

    result = edits.strip(text, "python")

    assert result == text


def test_a_python_file_with_an_unclosed_string_is_refused() -> None:
    text = 'x = """\n# [lma:threads]\n# keep me\n'

    with pytest.raises(ValueError, match="never closed"):
        edits.strip(text, "python")


@pytest.mark.parametrize(
    "original, position",
    [
        ("\n```py\nx\n```\n", 1),
        ("\n```py\nx\n```\n", 12),
        ("\n```py\nx\n````\n", 0),
    ],
)
def test_points_near_markdown_fences_round_trip(original: str, position: int) -> None:
    added = edits.add_comment(
        original, "markdown", position, position, author="a", body="b", at=_AT
    )
    commented = edits.apply(original, added.edits)
    doc = parse.parse(commented, "markdown")
    assert (doc.anchor(added.comment_id) is not None, doc.errors) == (True, ())

    result = edits.strip(commented, "markdown")

    assert result == original


@pytest.mark.parametrize(
    "kind, original, anchored, expected",
    [
        ("python", "x = 1", "x = 1", "x = 1\n"),
        ("markdown", "Before.\n\n```py\nx = 1\n```", "x = 1", "Before.\n\n```py\nx = 1\n```\n"),
    ],
)
def test_commenting_on_a_last_line_with_no_newline_leaves_one(
    kind: model.FileKind, original: str, anchored: str, expected: str
) -> None:
    start = original.index(anchored)
    added = edits.add_comment(
        original, kind, start, start + len(anchored), author="a", body="b", at=_AT
    )

    result = edits.strip(edits.apply(original, added.edits), kind)

    assert result == expected


def test_a_marker_keeps_its_removal_rule_after_the_text_beside_it_is_deleted() -> None:
    added = edits.add_comment(
        "x\n", "markdown", 0, 0, author="a", body="b", at=_AT, comment_id="Point"
    )
    commented = edits.apply("x\n", added.edits).replace("-->x", "-->", 1)

    result = edits.strip(commented, "markdown")

    assert result == "\n"


def test_an_own_line_marker_with_text_beside_it_removes_only_itself() -> None:
    text = '<!-- [lma:K7]: -->typed here\n\n<!-- [lma:threads]\n{"id": "K7", "author": "a", "at": "2026-11-19T19:40:00Z", "body": "b"}\n-->\n'

    result = edits.strip(text, "markdown")

    assert result == "typed here\n"


@pytest.mark.parametrize(
    "text",
    [
        "> ```md\n> <!-- [lma:threads]\n> keep me\n> -->\n> ```\n",
        "    <!-- [lma:threads]\n    keep me\n    -->\n",
        "# [lma:threads] in a sentence\n# keep me\n",
    ],
)
def test_a_threads_header_that_isn_t_a_whole_line_at_column_zero_is_text(text: str) -> None:
    result = edits.strip(text, "markdown" if "<!--" in text else "python")

    assert result == text


def test_a_section_with_a_line_that_isn_t_a_record_is_refused() -> None:
    text = "x = 1\n\n# [lma:threads]\n# not a record\n"

    with pytest.raises(ValueError, match="isn't a record"):
        edits.strip(text, "python")


def test_a_python_comment_after_a_string_s_closing_quotes_is_not_a_marker() -> None:
    text = 'value = """\nkeep me\n""" # [lma:Example]\nprint(value)\n'

    result = edits.strip(text, "python")

    assert result == text


@pytest.mark.parametrize(
    "text",
    [
        "    <!-- [lma:Example]: -->\n    plain literal\n",
        "> ~~~md\n> <!-- [lma:Example] -->\n> ~~~\n",
    ],
)
def test_markdown_marker_examples_in_code_blocks_stay(text: str) -> None:
    result = edits.strip(text, "markdown")

    assert result == text


def test_a_list_item_s_indented_continuation_is_not_code() -> None:
    record = '{"id": "K7", "author": "a", "at": "2026-11-19T19:40:00Z", "body": "b"}'
    text = f"- item\n\n    more <!-- [lma:K7] -->text\n\n<!-- [lma:threads]\n{record}\n-->\n"

    result = edits.strip(text, "markdown")

    assert result == "- item\n\n    more text\n"


def test_a_range_ending_on_an_own_line_marker_keeps_it_on_its_line() -> None:
    point = edits.add_comment("x\n", "markdown", 2, 2, author="a", body="one", at=_AT)
    commented = edits.apply("x\n", point.edits)
    section = parse.parse(commented, "markdown").section
    assert section is not None
    ranged = edits.add_comment(
        commented, "markdown", 0, section.start, author="a", body="two", at=_AT
    )
    commented = edits.apply(commented, ranged.edits)

    result = edits.strip(commented, "markdown")

    assert result == "x\n"


def test_any_unreadable_record_stops_strip() -> None:
    text = '<!-- [lma:Root] -->x\n\n<!-- [lma:threads]\n{"id": "Root", "author": "a", "at": "2026-11-19T20:00:00Z"}\n-->\n'

    with pytest.raises(ValueError, match="isn't a record"):
        edits.strip(text, "markdown")


def test_a_reply_s_id_doesn_t_own_a_marker() -> None:
    root = '{"id": "Root", "author": "a", "at": "2026-11-19T19:40:00Z", "body": "b"}'
    reply = (
        '{"id": "Example", "re": "Root", "author": "a", "at": "2026-11-19T19:41:00Z", "body": "c"}'
    )
    text = (
        "<!-- [lma:Root] -->Review.\n\n>     <!-- [lma:Example] -->\n>     literal\n"
        f"\n<!-- [lma:threads]\n{root}\n{reply}\n-->\n"
    )

    result = edits.strip(text, "markdown")

    assert result == "Review.\n\n>     <!-- [lma:Example] -->\n>     literal\n"


def test_an_id_with_two_openings_is_refused() -> None:
    added = edits.add_comment(
        "Review this.\n", "markdown", 0, 0, author="a", body="b", at=_AT, comment_id="Example"
    )
    commented = edits.apply("Review this.\n", added.edits)
    section = parse.parse(commented, "markdown").section
    assert section is not None
    example = "\n>     <!-- [lma:Example] -->\n>     literal\n"
    commented = commented[: section.start] + example + commented[section.start :]

    with pytest.raises(ValueError, match="more than one opening"):
        edits.strip(commented, "markdown")


def test_a_closing_marker_before_its_opening_one_is_refused() -> None:
    added = edits.add_comment(
        "Review this.\n", "markdown", 0, 0, author="a", body="b", at=_AT, comment_id="Root"
    )
    commented = ">     <!-- [/lma:Root] -->\n>     literal\n\n" + edits.apply(
        "Review this.\n", added.edits
    )

    with pytest.raises(ValueError, match="closes before it opens"):
        edits.strip(commented, "markdown")
