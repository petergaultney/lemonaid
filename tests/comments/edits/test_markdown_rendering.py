"""A comment never changes how a Markdown document renders: with the comments still in it,
the document renders as it did before, once the HTML comments are taken out of the result.
Stripping the comments back to the original text doesn't show this, since the file can
round-trip while its rendering with the comments in it does not."""

import re

import pytest
from markdown_it import MarkdownIt

from lemonaid.comments import edits, parse

_AT = "2026-11-23T10:00:00Z"
_DOC = """\
# Title

Intro paragraph line one,
line two of the intro.

## Section with *emphasis*

- first item
- second item
  continued item text
- third item

  a second paragraph in the item

1. one
2. two

> quoted line one
> quoted line two

Setext heading
--------------

Text before a rule.

| a | b |
|---|---|
| one | two |
| three | four |

***

Hard break here  
next line.

Back\\
slash break.

```py
code = 1
```

    indented code

Last paragraph.
"""
_RENDER = MarkdownIt("commonmark").enable("table")  # GitHub's Markdown has tables
# an HTML block takes its line break with it; an inline comment leaves the text's own
_OWN_LINE_COMMENTS = re.compile(r"^<!--.*?-->\n", re.S | re.M)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)


def _rendered(text: str) -> str:
    """The HTML, without comments and the `<wbr>` workaround in front of some markers."""
    html = _COMMENTS.sub("", _OWN_LINE_COMMENTS.sub("", _RENDER.render(text)))
    return html.replace("<wbr>", "")


_DELIMITER_ROW = "|---|---|"
# lines with no text to comment on, which `add` refuses
_REFUSED = (_DELIMITER_ROW, "***", "--------------")


def _selections() -> list[tuple[str, int, int]]:
    """For each non-blank line `add` accepts: the whole line, its first word, and a point
    at its start."""
    found = []
    offset = 0
    for line in _DOC.split("\n"):
        content = line.strip()
        if content and content not in _REFUSED:
            start = offset + line.index(content)
            first_word = content.split()[0]
            found += [
                (f"line {line!r}", start, start + len(content)),
                (f"first word of {line!r}", start, start + len(first_word)),
                (f"point at {line!r}", start, start),
            ]
        offset += len(line) + 1
    return found


@pytest.mark.parametrize(("what", "start", "end"), _selections(), ids=lambda v: str(v))
def test_a_comment_leaves_the_rendering_unchanged(what: str, start: int, end: int) -> None:
    added = edits.add_comment(_DOC, "markdown", start, end, author="a", body="b", at=_AT)

    commented = edits.apply(_DOC, added.edits)

    doc = parse.parse(commented, "markdown")
    assert doc.errors == ()
    assert _rendered(commented) == _rendered(_DOC), what


@pytest.mark.parametrize(
    ("selected", "anchored"),
    [
        ("# Title", "Title"),
        ("- second item", "second item"),
        ("line two of the intro.", "line two of the intro."),
        ("> quoted line two", "quoted line two"),
        ("Last paragraph.", "Last paragraph."),
    ],
)
def test_the_anchor_starts_at_the_selected_text(selected: str, anchored: str) -> None:
    start = _DOC.index(selected)
    added = edits.add_comment(
        _DOC, "markdown", start, start + len(selected), author="a", body="b", at=_AT
    )

    commented = edits.apply(_DOC, added.edits)

    anchor = parse.parse(commented, "markdown").anchors[0]
    assert commented[anchor.start : anchor.end] == anchored


@pytest.mark.parametrize(
    ("text", "line", "why"),
    [
        (_DOC, _DELIMITER_ROW, "delimiter row"),
        ("> | a | b |\n> |---|---|\n> | c | d |\n", "> |---|---|", "delimiter row"),
        (_DOC, "***", "rule"),
        (_DOC, "--------------", "rule"),
        ("##\n\ntext\n", "##", "heading with no text"),
        ("# ###\n\ntext\n", "# ###", "heading with no text"),
        ("---\ntype: Brief\n---\n\nBody.\n", "---", "frontmatter"),
        ("---\ntype: Brief\n---\n\nBody.\n", "type: Brief", "frontmatter"),
        ("---\ntype: Brief\n---\n\nBody.\n", "Brief", "frontmatter"),
    ],
)
def test_a_line_no_marker_can_hide_in_is_refused(text: str, line: str, why: str) -> None:
    start = text.index(line)

    with pytest.raises(ValueError, match=why):
        edits.add_comment(text, "markdown", start, start + len(line), author="a", body="b", at=_AT)


def test_the_closing_frontmatter_delimiter_is_refused_too() -> None:
    text = "---\ntype: Brief\n---\n\nBody.\n"
    start = text.index("---", 3)

    with pytest.raises(ValueError, match="frontmatter"):
        edits.add_comment(text, "markdown", start, start + 3, author="a", body="b", at=_AT)


def test_a_comment_after_frontmatter_is_accepted() -> None:
    text = "---\ntype: Brief\n---\n\nBody.\n"
    start = text.index("Body.")
    added = edits.add_comment(text, "markdown", start, start + 5, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert commented.startswith("---\ntype: Brief\n---\n")


def test_a_heading_s_closing_hashes_stay_after_the_comment() -> None:
    text = "# Title ###\n"
    added = edits.add_comment(text, "markdown", 0, 11, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert commented.startswith("# <!-- [lma:") and "Title<!-- [/lma:" in commented
    assert _rendered(commented) == _rendered(text)


def test_a_point_in_a_code_span_at_a_line_s_start_keeps_the_line() -> None:
    text = "`code` and text\n"
    added = edits.add_comment(text, "markdown", 2, 2, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert _rendered(commented) == _rendered(text)


def test_every_comment_the_rules_place_is_checked_by_rendering(monkeypatch) -> None:
    """The render check is a net under the rules: a placement that would change the
    rendering is refused, whatever put it there."""
    from lemonaid.comments.kinds import markdown

    monkeypatch.setattr(
        markdown,
        "_opening_inline",
        lambda text, position, comment_id: markdown.model.Edit(
            position, position, f"<!-- [lma:{comment_id}] -->"
        ),
    )
    start = _DOC.index("- second item")

    with pytest.raises(ValueError, match="change how the document renders"):
        edits.add_comment(_DOC, "markdown", start, start + 13, author="a", body="b", at=_AT)


def test_a_comment_after_a_table_with_no_body_rows_leaves_the_table_alone() -> None:
    text = "| h |\n|---|\n\nAfter.\n"
    start = text.index("After.")
    added = edits.add_comment(text, "markdown", start, start + 6, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert _rendered(commented) == _rendered(text)


@pytest.mark.parametrize(
    ("text", "selected"),
    [
        ("[site]: https://example.com\n\n[site].\n", "[site]."),
        ("> ~~~\n> code\n> ~~~\n> continued\n", "continued"),
        ("- parent\n  - child\n    ***\n    tail\n- next\n", "tail"),
        ("first  \nnext text\n", "next text"),
        ("first\\\nnext text\n", "next text"),
        ("Setext\n> - item\n>   cont *x*\n", "cont *x*"),
    ],
)
def test_the_cases_the_line_before_approach_broke_render_the_same(text: str, selected: str) -> None:
    start = text.index(selected)
    added = edits.add_comment(
        text, "markdown", start, start + len(selected), author="a", body="b", at=_AT
    )

    commented = edits.apply(text, added.edits)

    anchor = parse.parse(commented, "markdown").anchors[0]
    assert _rendered(commented) == _rendered(text)
    assert commented[anchor.start : anchor.end] == selected


def test_a_comment_on_a_link_definition_is_refused() -> None:
    text = "[site]: https://example.com\n\n[site].\n"

    with pytest.raises(ValueError, match="change how the document renders"):
        edits.add_comment(text, "markdown", 0, 27, author="a", body="b", at=_AT)


def test_a_second_point_at_a_line_s_start_leaves_the_first_where_it_was() -> None:
    text = "above\nbelow\n"
    start = text.index("below")
    first = edits.add_comment(text, "markdown", start, start, author="a", body="b", at=_AT)
    once = edits.apply(text, first.edits)
    second_at = once.index("below")
    second = edits.add_comment(once, "markdown", second_at, second_at, author="a", body="c", at=_AT)

    twice = edits.apply(once, second.edits)

    anchors = parse.parse(twice, "markdown").anchors
    assert [twice.count("\n", 0, a.start) for a in anchors] == [1, 1]  # both on `below`
    assert _rendered(twice) == _rendered(text)


@pytest.mark.parametrize(
    ("text", "selected"),
    [
        ("- text<wbr>\n", "- text<wbr>"),
        ("- text<wbr>\r\n", "- text<wbr>"),
        ("a <wbr>word here\n", "word"),
    ],
)
def test_a_wbr_someone_wrote_survives_strip(text: str, selected: str) -> None:
    start = text.index(selected)
    added = edits.add_comment(
        text, "markdown", start, start + len(selected), author="a", body="b", at=_AT
    )

    stripped = edits.strip(edits.apply(text, added.edits), "markdown")

    assert stripped == text


def test_a_comment_inside_a_raw_html_attribute_is_refused() -> None:
    text = '<div class="important">Label</div>\n'
    start = text.index("important")

    with pytest.raises(ValueError, match="change how the document renders"):
        edits.add_comment(text, "markdown", start, start + 9, author="a", body="b", at=_AT)


@pytest.mark.parametrize(
    "text", ["﻿---\r\ntype: Brief\r\n---\r\n\r\n# Heading\r\n", "---\ntype: Brief\n---\n"]
)
def test_frontmatter_after_a_byte_order_mark_is_refused_too(text: str) -> None:
    start = text.index("type")

    with pytest.raises(ValueError, match="frontmatter"):
        edits.add_comment(text, "markdown", start, start + 4, author="a", body="b", at=_AT)


def test_an_empty_frontmatter_block_ends_at_its_own_closer() -> None:
    text = "---\n---\n\nPara.\n\n---\n"
    start = text.index("Para.")
    added = edits.add_comment(text, "markdown", start, start + 5, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert _rendered(commented) == _rendered(text)


@pytest.mark.parametrize(
    ("text", "selected"),
    [
        ("```text\n---\n```\n", "---"),
        ("A paragraph\n|---|---|\nwith a row-shaped line.\n", "|---|---|"),
    ],
)
def test_a_line_shaped_like_a_rule_or_delimiter_but_not_one_is_accepted(
    text: str, selected: str
) -> None:
    start = text.index(selected)
    added = edits.add_comment(text, "markdown", start, start, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert _rendered(commented) == _rendered(text)


@pytest.mark.parametrize(
    ("text", "selected"),
    [
        ('<div>A<wbr class="important">B</div>\n', "important"),
        ("<textarea>visible text here</textarea>\n", "visible text"),
        ("<title>visible text here</title>\n", "visible text"),
        ("<textarea></title>visible text here</textarea>\n", "visible text"),
        ("<plaintext></plaintext>visible text here\n", "visible text"),
    ],
)
def test_a_comment_that_would_change_raw_html_is_refused(text: str, selected: str) -> None:
    start = text.index(selected)

    with pytest.raises(ValueError, match="change how the document renders"):
        edits.add_comment(
            text, "markdown", start, start + len(selected), author="a", body="b", at=_AT
        )


@pytest.mark.parametrize("element", ["textarea", "title"])
def test_a_comment_inside_raw_text_counts_as_text_whatever_the_python(element: str) -> None:
    """Some Python versions' HTML parsers report `<!-- -->` in a textarea as a comment; a
    browser shows it as text, and so does the check."""
    from lemonaid.comments.kinds import markdown

    parts = markdown._shown(f"<{element}><!-- x --></{element}>")

    assert ("text", "<!-- x -->") in parts


def test_a_pipe_line_that_makes_no_table_is_not_refused_as_a_delimiter() -> None:
    text = "a | b | c\n|---|---|\n"
    start = text.index("|---|")
    added = edits.add_comment(text, "markdown", start, start, author="a", body="b", at=_AT)

    commented = edits.apply(text, added.edits)

    assert _rendered(commented) == _rendered(text)
