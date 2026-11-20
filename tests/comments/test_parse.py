import textwrap

import pytest

from lemonaid.comments import model, parse

_AT = "2026-11-19T19:40:00Z"
_LINE_SEPARATOR = chr(0x2028)
_BACKTICK = chr(0x60)


def _record(comment_id: str, body: str = "why?", **fields: str) -> str:
    extra = "".join(f', "{k}": "{v}"' for k, v in fields.items())
    return f'{{"id": "{comment_id}"{extra}, "author": "caleb.gregory", "at": "{_AT}", "body": "{body}"}}'


def test_a_python_range_anchor_covers_the_lines_between_its_markers() -> None:
    text = textwrap.dedent(
        f"""\
        def f():
            # [lma:SleepRib]
            x = 1
            return x
            # [/lma:SleepRib]

        # [lma:threads]
        # {_record("SleepRib")}
        """
    )
    opening = (text.index("    # [lma:SleepRib]"), text.index("    x = 1"))
    closing = (text.index("    # [/lma:SleepRib]"), text.index("\n# [lma:threads]"))

    result = parse.parse(text, "python")

    assert result == model.Document(
        kind="python",
        markers=(
            model.Marker("SleepRib", closing=False, carrier=opening),
            model.Marker("SleepRib", closing=True, carrier=closing),
        ),
        anchors=(
            model.Anchor(
                "SleepRib", start=opening[1], end=closing[0], opening=opening, closing=closing
            ),
        ),
        comments=(
            model.Comment(
                id="SleepRib",
                author="caleb.gregory",
                at=_AT,
                body="why?",
                offset=text.index('# {"id"'),
            ),
        ),
        resolutions=(),
        errors=(),
        section=model.Section(
            start=text.index("\n# [lma:threads]"), insert_at=len(text), end=len(text), closed=True
        ),
        newline="\n",
        unclosed_string=None,
    )
    assert text[opening[1] : closing[0]] == "    x = 1\n    return x\n"


def test_a_python_point_anchor_covers_the_next_line() -> None:
    text = f"# [lma:TinOwl]\nx = 1\ny = 2\n\n# [lma:threads]\n# {_record('TinOwl')}\n"

    result = parse.parse(text, "python")

    anchor = result.anchors[0]
    assert (text[anchor.start : anchor.end], anchor.closing, result.errors) == ("x = 1", None, ())


def test_markdown_anchors_sit_inline_in_html_comments() -> None:
    text = textwrap.dedent(
        f"""\
        We <!-- [lma:SleepRib] -->drop the row<!-- [/lma:SleepRib] --> here.<!-- [lma:TinOwl] -->

        <!-- [lma:threads]
        {_record("SleepRib")}
        {_record("TinOwl")}
        -->
        """
    )

    result = parse.parse(text, "markdown")

    spans = [(a.id, text[a.start : a.end]) for a in result.anchors]
    assert (spans, result.errors) == ([("SleepRib", "drop the row"), ("TinOwl", "")], ())
    assert [c.id for c in result.comments] == ["SleepRib", "TinOwl"]


def test_markdown_markers_spelled_for_their_own_lines_wrap_paragraphs() -> None:
    text = f"<!-- [lma:K7]: -->\nOne.\n\nTwo.\n<!-- [/lma:K7]: -->\nAfter.\n\n<!-- [lma:threads]\n{_record('K7')}\n-->\n"

    result = parse.parse(text, "markdown")

    anchor = result.anchors[0]
    assert (text[anchor.start : anchor.end], result.errors) == ("One.\n\nTwo.\n", ())


def test_markdown_markers_inside_code_are_examples_not_markers() -> None:
    text = textwrap.dedent(
        """\
        Write `<!-- [lma:k7] -->` around a phrase.

        ```markdown
        <!-- [lma:threads]
        {"id": "k7"}
        -->
        ```
        """
    )

    result = parse.parse(text, "markdown")

    assert (result.markers, result.comments, result.errors, result.section) == ((), (), (), None)


def test_python_markers_inside_a_string_are_text() -> None:
    text = 'DOC = """\n# [lma:K7]\n# [lma:threads]\n"""\nprint(DOC)\n'

    result = parse.parse(text, "python")

    assert (result.markers, result.section, result.errors) == ((), None, ())


def test_a_markdown_backtick_in_a_record_can_t_hide_the_section() -> None:
    body = f"Try {_BACKTICK}len{_BACKTICK}."
    text = (
        f"Use {_BACKTICK} <!-- [lma:K7] -->here.\n\n<!-- [lma:threads]\n"
        f'{{"id": "K7", "author": "a", "at": "{_AT}", "body": "{body}"}}\n-->\n'
    )

    result = parse.parse(text, "markdown")

    assert ([c.body for c in result.comments], result.errors) == ([body], ())


def test_crlf_files_parse_like_lf_files() -> None:
    python = f"# [lma:K7]\nx = 1\n# [/lma:K7]\n\n# [lma:threads]\n# {_record('K7')}\n"
    markdown = f"<!-- [lma:K7] -->x<!-- [/lma:K7] -->\n\n<!-- [lma:threads]\n{_record('K7')}\n-->\n"

    results = [
        parse.parse(python.replace("\n", "\r\n"), "python"),
        parse.parse(markdown.replace("\n", "\r\n"), "markdown"),
    ]

    assert [(len(r.anchors), len(r.comments), r.errors, r.newline) for r in results] == [
        (1, 1, (), "\r\n"),
        (1, 1, (), "\r\n"),
    ]
    python_anchor = results[0].anchors[0]
    assert python.replace("\n", "\r\n")[python_anchor.start : python_anchor.end] == "x = 1\r\n"


def test_a_line_separator_inside_a_record_does_not_split_it() -> None:
    text = (
        "# [lma:K7]\nx = 1\n\n# [lma:threads]\n"
        f'# {{"id": "K7", "author": "a", "at": "{_AT}", "body": "a{_LINE_SEPARATOR}b"}}\n'
    )

    result = parse.parse(text, "python")

    assert ([c.body for c in result.comments], result.errors) == ([f"a{_LINE_SEPARATOR}b"], ())


def test_markdown_bodies_may_escape_angle_brackets() -> None:
    escaped = "\\" + "u003e"
    text = (
        "<!-- [lma:K7] -->\n\n<!-- [lma:threads]\n"
        f'{{"id": "K7", "author": "a", "at": "{_AT}", "body": "a --{escaped} b"}}\n-->\n'
    )

    result = parse.parse(text, "markdown")

    assert result.comments[0].body == "a --> b"


def test_unknown_fields_are_kept_apart() -> None:
    text = f'# [lma:threads]\n# {{"id": "K7", "author": "a", "at": "{_AT}", "body": "b", "mood": "curious"}}\n'

    result = parse.parse(text, "python")

    assert result.comments[0].extra == {"mood": "curious"}


def test_a_reply_and_a_resolution_are_read_from_their_fields() -> None:
    text = (
        "# [lma:K7]\nx = 1\n\n# [lma:threads]\n"
        f"# {_record('K7')}\n"
        f'# {{"id": "M2", "re": "K7", "span": [0, 3], "author": "BraveFig", "at": "{_AT}", "body": "b"}}\n'
        f'# {{"resolves": "M2", "author": "caleb.gregory", "at": "{_AT}"}}\n'
    )

    result = parse.parse(text, "python")

    assert (result.comments[1].re, result.comments[1].span, result.errors) == ("K7", (0, 3), ())
    assert result.resolutions == (
        model.Resolution(
            resolves="M2", author="caleb.gregory", at=_AT, offset=text.index('# {"resolves"')
        ),
    )


@pytest.mark.parametrize(
    "records, message",
    [
        (["not json"], "a record is not JSON: Expecting value"),
        (['["a list"]'], "a record is not a JSON object"),
        ([f'{{"id": "K7", "at": "{_AT}", "body": "b"}}'], "a record has no author"),
        (
            ['{"id": "K7", "author": "a", "at": "yesterday", "body": "b"}'],
            "a record's `at` is not an ISO 8601 time in UTC",
        ),
        (
            ['{"id": "K7", "author": "a", "at": "2026-11-19", "body": "b"}'],
            "a record's `at` is not an ISO 8601 time in UTC",
        ),
        (
            ['{"id": "K7", "author": "a", "at": "2026-11-19T14:40:00-05:00", "body": "b"}'],
            "a record's `at` is not an ISO 8601 time in UTC",
        ),
        ([f'{{"id": "K7", "author": "a", "at": "{_AT}"}}'], "comment K7 has no body"),
        ([_record("K7"), _record("K7")], "comment id K7 is used twice"),
        ([_record("K7"), _record("M2", re="Gone")], "comment M2 answers Gone, which doesn't exist"),
        (
            [
                _record("K7"),
                f'{{"id": "M2", "re": "K7", "span": [0, 99], "author": "a", "at": "{_AT}", "body": "b"}}',
            ],
            "comment M2's span runs past the end of K7",
        ),
        (
            [
                _record("K7"),
                f'{{"id": "M2", "span": [0, 1], "author": "a", "at": "{_AT}", "body": "b"}}',
            ],
            "comment M2 has a `span` but answers no comment",
        ),
        (
            [_record("K7"), f'{{"resolves": "Gone", "author": "a", "at": "{_AT}"}}'],
            "a resolution names Gone, which doesn't exist",
        ),
        (
            [_record("K7"), _record("A1", re="B2"), _record("B2", re="A1")],
            "comment A1 is not part of any thread",
        ),
    ],
)
def test_a_bad_record_is_reported_and_the_rest_still_read(records: list[str], message: str) -> None:
    text = "# [lma:K7]\nx = 1\n\n# [lma:threads]\n" + "".join(f"# {r}\n" for r in records)

    result = parse.parse(text, "python")

    assert message in [e.message for e in result.errors]
    assert result.anchors[0].id == "K7"


@pytest.mark.parametrize(
    "body, message",
    [
        ("# [lma:K7]\n# [lma:K7]\nx\n# [/lma:K7]\n", "anchor K7 opens twice"),
        ("# [/lma:K7]\nx\n# [lma:K7]\n", "anchor K7 closes before it opens"),
        ("# [lma:K7]\nx\n# [/lma:K7]\n# [/lma:K7]\n", "anchor K7 is closed twice"),
        ("# [lma:K7]\nx\n# [lma:Lost]\ny\n", "anchor Lost has no comment"),
    ],
)
def test_a_bad_anchor_is_reported(body: str, message: str) -> None:
    text = f"{body}\n# [lma:threads]\n# {_record('K7')}\n"

    result = parse.parse(text, "python")

    assert message in [e.message for e in result.errors]


def test_a_threads_marker_in_the_body_is_not_a_marker() -> None:
    text = f"    # [lma:threads]\n# [lma:K7]\nx\n\n# [lma:threads]\n# {_record('K7')}\n"

    result = parse.parse(text, "python")

    assert ([m.id for m in result.markers], result.errors) == (["K7"], ())


def test_text_after_a_markdown_threads_section_is_reported() -> None:
    text = f"<!-- [lma:K7] -->\n\n<!-- [lma:threads]\n{_record('K7')}\n-->\nmore prose\n"

    result = parse.parse(text, "markdown")

    assert [e.message for e in result.errors] == ["text follows the threads section"]
    assert result.section is not None
    assert text[result.section.end :] == "more prose\n"


def test_a_markdown_threads_section_without_its_closing_runs_to_the_end() -> None:
    text = f"<!-- [lma:K7] -->\n\n<!-- [lma:threads]\n{_record('K7')}\n"

    result = parse.parse(text, "markdown")

    assert [e.message for e in result.errors] == ["the threads section has no closing -->"]
    assert [c.id for c in result.comments] == ["K7"]


def test_a_closing_fence_longer_than_the_opening_one_closes_it() -> None:
    text = f"```py\nx\n````\n<!-- [lma:K7] -->after\n\n<!-- [lma:threads]\n{_record('K7')}\n-->\n"

    result = parse.parse(text, "markdown")

    assert ([a.id for a in result.anchors], [c.id for c in result.comments], result.errors) == (
        ["K7"],
        ["K7"],
        (),
    )


def test_an_unclosed_python_string_is_reported() -> None:
    text = 'x = 1\ny = """\nstill typing\n'

    result = parse.parse(text, "python")

    assert [e.message for e in result.errors] == ["a string starts here and is never closed"]
    assert result.unclosed_string is not None
    assert text[result.unclosed_string :].lstrip().startswith('"""')


def test_markers_alone_and_adjacent_never_make_a_backwards_anchor() -> None:
    text = "# [lma:A]\n# [/lma:A]"

    result = parse.parse(text, "python")

    assert [(a.start, a.end) for a in result.anchors] == [(10, 10)]


@pytest.mark.parametrize(
    "extra",
    [
        "9" * 4301,
        "[" * 100_000 + "]" * 100_000,
    ],
)
def test_a_record_past_the_decoder_s_limits_is_an_error(extra: str) -> None:
    text = (
        "# [lma:K7]\nx = 1\n\n# [lma:threads]\n"
        f"# {_record('K7')}\n"
        f'# {{"id": "M2", "re": "K7", "author": "a", "at": "{_AT}", "body": "b", "big": {extra}}}\n'
    )

    result = parse.parse(text, "python")

    assert [e.message for e in result.errors] == ["a record is too large to read"]
    assert [c.id for c in result.comments] == ["K7"]
