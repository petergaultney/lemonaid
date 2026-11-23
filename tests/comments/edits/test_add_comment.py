import textwrap

import pytest

from lemonaid.comments import edits, model, parse

_AT = "2026-11-19T19:40:00Z"
_RECORD = f'{{"id": "SleepRib", "author": "caleb.gregory", "at": "{_AT}", "body": "why?"}}'
_BACKTICK = chr(0x60)


def test_a_python_selection_grows_to_whole_lines_with_the_code_s_indent() -> None:
    text = textwrap.dedent(
        """\
        def f():
            if x:
                return 1
            return 2
        """
    )
    start, end = text.index("x:"), text.index("1") + 1

    result = edits.add_comment(
        text,
        "python",
        start,
        end,
        author="caleb.gregory",
        body="why?",
        at=_AT,
        comment_id="SleepRib",
    )

    assert edits.apply(text, result.edits) == textwrap.dedent(
        f"""\
        def f():
            # [lma:SleepRib]
            if x:
                return 1
            # [/lma:SleepRib]
            return 2

        # [lma:threads]
        # {_RECORD}
        """
    )


def test_a_linewise_python_selection_does_not_take_the_next_line() -> None:
    text = "a = 1\nb = 2\nc = 3\n"
    start, end = text.index("a"), text.index("c")

    result = edits.add_comment(
        text,
        "python",
        start,
        end,
        author="caleb.gregory",
        body="why?",
        at=_AT,
        comment_id="SleepRib",
    )

    assert edits.apply(text, result.edits).startswith(
        "# [lma:SleepRib]\na = 1\nb = 2\n# [/lma:SleepRib]\nc = 3\n"
    )


def test_an_empty_python_selection_anchors_its_line() -> None:
    text = "a = 1\nb = 2\n"
    position = text.index("b") + 2

    result = edits.add_comment(text, "python", position, position, author="a", body="b", at=_AT)

    commented = edits.apply(text, result.edits)
    doc = parse.parse(commented, "python")
    anchor = doc.anchor(result.comment_id)
    assert anchor is not None
    assert (commented[anchor.start : anchor.end], doc.errors) == ("b = 2", ())


def test_a_python_selection_inside_a_docstring_grows_to_the_whole_string() -> None:
    text = 'def f():\n    """One.\n\n    Two.\n    """\n    return 1\n'
    position = text.index("Two")

    result = edits.add_comment(
        text, "python", position, position + 3, author="a", body="b", at=_AT, comment_id="K7"
    )

    assert edits.apply(text, result.edits).startswith(
        'def f():\n    # [lma:K7]\n    """One.\n\n    Two.\n    """\n    # [/lma:K7]\n    return 1\n'
    )


@pytest.mark.parametrize(
    "text",
    [
        "#!/usr/bin/env python3\nprint(1)\n",
        "# -*- coding: latin-1 -*-\nprint(1)\n",
        "#!/usr/bin/env python3\n# coding: latin-1\nprint(1)\n",
    ],
)
def test_a_marker_can_t_go_above_a_shebang_or_encoding_line(text: str) -> None:
    with pytest.raises(ValueError, match="shebang or encoding"):
        edits.add_comment(text, "python", 0, 0, author="a", body="b", at=_AT)


def test_the_line_after_a_shebang_can_be_anchored() -> None:
    text = "#!/usr/bin/env python3\nprint(1)\n"
    position = text.index("print")

    result = edits.add_comment(
        text, "python", position, position, author="a", body="b", at=_AT, comment_id="K7"
    )

    assert edits.apply(text, result.edits).startswith(
        "#!/usr/bin/env python3\n# [lma:K7]\nprint(1)\n"
    )


def test_inserted_lines_use_the_file_s_line_ending() -> None:
    text = "a = 1\r\nb = 2\r\n"

    result = edits.add_comment(
        text, "python", 0, text.index("b"), author="a", body="b", at=_AT, comment_id="K7"
    )

    commented = edits.apply(text, result.edits)
    assert "\n" not in commented.replace("\r\n", "")
    assert parse.parse(commented, "python").errors == ()


def test_a_markdown_selection_is_wrapped_inline() -> None:
    text = "We drop the row here.\n"
    start = text.index("drop")

    result = edits.add_comment(
        text,
        "markdown",
        start,
        start + len("drop the row"),
        author="caleb.gregory",
        body="why?",
        at=_AT,
        comment_id="SleepRib",
    )

    assert edits.apply(text, result.edits) == (
        "We <!-- [lma:SleepRib] -->drop the row<!-- [/lma:SleepRib] --> here.\n"
        f"\n<!-- [lma:threads]\n{_RECORD}\n-->\n"
    )


def test_a_markdown_selection_inside_a_code_span_wraps_the_whole_span() -> None:
    text = f"Call {_BACKTICK}code{_BACKTICK} now.\n"
    start = text.index("code")

    result = edits.add_comment(
        text, "markdown", start, start + 4, author="a", body="b", at=_AT, comment_id="K7"
    )

    commented = edits.apply(text, result.edits)
    doc = parse.parse(commented, "markdown")
    anchor = doc.anchor("K7")
    assert anchor is not None
    assert (commented[anchor.start : anchor.end], doc.errors) == (
        f"{_BACKTICK}code{_BACKTICK}",
        (),
    )


def test_markers_around_a_fenced_block_take_their_own_lines() -> None:
    text = "Before.\n\n```py\nx = 1\n```\nAfter.\n"
    start = text.index("x = 1")

    result = edits.add_comment(
        text, "markdown", start, start + 5, author="a", body="b", at=_AT, comment_id="K7"
    )

    commented = edits.apply(text, result.edits)
    assert commented.startswith(
        "Before.\n\n<!-- [lma:K7]: -->\n```py\nx = 1\n```\n<!-- [/lma:K7]: -->\nAfter.\n"
    )
    assert parse.parse(commented, "markdown").errors == ()


def test_a_second_thread_joins_the_existing_section() -> None:
    text = "a = 1\nb = 2\n"
    first = edits.add_comment(text, "python", 0, 0, author="a", body="one", at=_AT)
    text = edits.apply(text, first.edits)
    position = text.index("b")

    result = edits.add_comment(text, "python", position, position, author="a", body="two", at=_AT)

    doc = parse.parse(edits.apply(text, result.edits), "python")
    assert ([c.body for c in doc.comments], doc.errors) == (["one", "two"], ())


def test_a_new_id_is_a_wordybin_name() -> None:
    result = edits.add_comment("a = 1\n", "python", 0, 0, author="a", body="b", at=_AT)

    assert model.ID.fullmatch(result.comment_id)


def test_a_range_in_the_threads_section_is_refused() -> None:
    text = f"a = 1\n\n# [lma:threads]\n# {_RECORD}\n"

    with pytest.raises(ValueError, match="not in the file's body"):
        edits.add_comment(text, "python", len(text) - 2, len(text) - 1, author="a", body="b")


@pytest.mark.parametrize(
    "text",
    [
        'x = ("""a\nb""", 1)\nafter = 2\n',
        "x = 1 + \\\n    2\nafter = 2\n",
    ],
)
def test_python_markers_never_land_inside_a_string_or_a_continued_line(text: str) -> None:
    result = edits.add_comment(text, "python", 0, 1, author="a", body="b", at=_AT)

    commented = edits.apply(text, result.edits)
    compile(commented, "<commented>", "exec")
    assert edits.strip(commented, "python") == text
    assert commented.index("# [/lma:") < commented.index("after")


def test_an_encoding_line_after_a_unicode_separator_is_still_protected() -> None:
    text = f'# first{chr(0x85)}line\n# coding: latin-1\nprint("x")\n'

    with pytest.raises(ValueError, match="shebang or encoding"):
        edits.add_comment(text, "python", 0, 0, author="a", body="b", at=_AT)


def test_a_python_file_with_an_unclosed_string_can_t_be_commented() -> None:
    with pytest.raises(ValueError, match="never closed"):
        edits.add_comment('x = 1\ny = """\nopen\n', "python", 0, 0, author="a", body="b", at=_AT)


def test_a_bare_cr_file_is_refused() -> None:
    with pytest.raises(ValueError, match="bare CR"):
        edits.add_comment("x\r", "python", 0, 0, author="a", body="b", at=_AT)


def test_a_comment_the_file_s_layout_would_hide_is_refused() -> None:
    text = "```md\nexample\n"

    with pytest.raises(ValueError, match="wouldn't read back as intended"):
        edits.add_comment(text, "markdown", 0, 0, author="a", body="b", at=_AT)


def test_a_reused_id_is_refused() -> None:
    added = edits.add_comment(
        "x = 1\n", "python", 0, 0, author="a", body="b", at=_AT, comment_id="Root"
    )
    text = edits.apply("x = 1\n", added.edits)

    with pytest.raises(ValueError, match="already used"):
        edits.add_comment(text, "python", 0, 0, author="a", body="b", at=_AT, comment_id="Root")


def test_a_point_inside_an_existing_marker_goes_after_it() -> None:
    text = "a x\ny\n"
    ranged = edits.add_comment(
        text, "markdown", 2, 3, author="a", body="b", at=_AT, comment_id="Old"
    )
    commented = edits.apply(text, ranged.edits)
    inside = commented.index("<!-- [lma:Old] -->") + 5

    result = edits.add_comment(commented, "markdown", inside, inside, author="a", body="b", at=_AT)

    doc = parse.parse(edits.apply(commented, result.edits), "markdown")
    assert (sorted(a.id for a in doc.anchors), doc.errors) == (
        sorted(["Old", result.comment_id]),
        (),
    )


def test_a_markdown_offset_between_cr_and_lf_moves_before_the_cr() -> None:
    text = "x\r\n"

    result = edits.add_comment(text, "markdown", 2, 2, author="a", body="b", at=_AT)

    commented = edits.apply(text, result.edits)
    reply = edits.reply(commented, "markdown", result.comment_id, author="Claude", body="c", at=_AT)
    assert edits.strip(edits.apply(commented, reply.edits), "markdown") == text


@pytest.mark.parametrize(
    "text",
    [
        "> ~~~md\n> sample\n>~~~\n\nAfter.\n",
        "> ~~~md\n> sample\n\nAfter.\n",
    ],
)
def test_a_quoted_fence_ends_with_its_closer_or_its_quote(text: str) -> None:
    position = text.index("After")

    result = edits.add_comment(
        text, "markdown", position, position + 5, author="a", body="b", at=_AT
    )

    assert edits.strip(edits.apply(text, result.edits), "markdown") == text


@pytest.mark.parametrize(
    "text",
    [
        "> ~~~md\n> sample\n~~~py\nx\n~~~\n\nAfter.\n",
        "    ~~~\n    verbatim\n\nAfter.\n",
    ],
)
def test_text_after_these_code_blocks_can_be_commented(text: str) -> None:
    position = text.index("After")

    result = edits.add_comment(
        text, "markdown", position, position + 5, author="a", body="b", at=_AT
    )

    assert edits.strip(edits.apply(text, result.edits), "markdown") == text


def test_a_one_line_code_span_with_three_backticks_is_not_a_fence() -> None:
    text = "```sample```\n\nAfter.\n"
    position = text.index("After")

    result = edits.add_comment(
        text, "markdown", position, position + 5, author="a", body="b", at=_AT
    )

    assert edits.strip(edits.apply(text, result.edits), "markdown") == text
