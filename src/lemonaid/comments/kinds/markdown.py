"""Markdown files: markers are HTML comments, inline or on lines of their own, and the
threads section is one HTML comment at the end. We find code ourselves: fences at any
block-quote depth, indented code blocks outside lists, and code spans."""

import html.parser
import re
import typing as ty

from .. import lines, model, records

# A `<wbr>` is part of the marker after it only when that marker is an opening one that
# says so (` wbr`), so a `<wbr>` someone wrote stays theirs: see `_WBR`.
_MARKER: ty.Final = re.compile(
    r"(?:<wbr>(?=<!--[ \t]*\[lma:[A-Za-z][\w-]*\][ \t]+wbr[ \t]*-->))?"
    r"<!--[ \t]*\[(?P<close>/)?lma:(?P<id>[A-Za-z][\w-]*)\](?P<own_line>:)?(?:[ \t]+wbr)?[ \t]*-->"
)
# A workaround. CommonMark reads a line whose text starts with `<!--` as an HTML block,
# not as Markdown, even when the text is a list item's or a block quote's, or a line in
# the middle of a paragraph (which it then ends): so a marker there would show the line's
# Markdown raw, or break up its list or paragraph. `<wbr>` (a "word break opportunity", an
# empty void element) renders nothing, and a line that starts with it is ordinary text.
# So where a comment starts a list item's, a quote's or a paragraph line's text, its
# opening marker is written `<wbr><!-- [lma:X] wbr -->`: the ` wbr` says the `<wbr>` is
# the marker's, so it goes when the marker does, and a `<wbr>` a person wrote never does.
# A heading's text and a table cell are inline already and need none.
# docs/comments.md, under Anchors, has the rules.
_WBR: ty.Final = "<wbr>"
_SECTION: ty.Final = re.compile(r"^<!-- \[lma:threads\]\r?$", re.M)
_SECTION_END: ty.Final = "-->"
_QUOTE_PREFIX: ty.Final = re.compile(r"(?: {0,3}>)*")
_FENCE_OPENER: ty.Final = re.compile(r" {0,3}(?P<fence>(?P<char>[`~])(?P=char){2,})")
_BLANK: ty.Final = re.compile(r"[ \t\r]*")
_INDENTED: ty.Final = re.compile(r"(?: {4}|\t)")
_LIST_ITEM: ty.Final = re.compile(r" {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_CODE_SPAN: ty.Final = re.compile(r"(`+)(?!`).*?(?<!`)\1(?!`)", re.S)
# block quote markers and list item markers at the start of a line, nested any way
_CONTAINERS: ty.Final = re.compile(r"(?: {0,3}>[ \t]?| {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+)*")
_HEADING: ty.Final = re.compile(r" {0,3}#{1,6}(?:[ \t]+|$)")
_TABLE_ROW: ty.Final = re.compile(r" {0,3}\|[ \t]*")
_CLOSING_HASHES: ty.Final = re.compile(r"[ \t]+#+[ \t]*$")
# a leading byte order mark, then `---` to the next `---` or `...` line, which may be the next
_FRONTMATTER: ty.Final = re.compile(
    r"\ufeff?---[ \t]*\r?\n(?:.*?\n)??(?:---|\.\.\.)[ \t]*(?:\r?\n|$)", re.S
)
# a line nothing may follow: a thematic break or a setext heading's underline
_RULE: ty.Final = re.compile(r" {0,3}(?:([-*_])(?:[ \t]*\1){2,}|=+|-+)[ \t]*\r?$")


def code_regions(text: str) -> list[model.CodeRegion]:
    """Fenced blocks, indented code blocks, then code spans in the text that is left."""
    fences = _fences(text)
    blocks = [*fences, *_indented_code(lines.masked(text, fences))]
    without_blocks = lines.masked(text, blocks)
    spans = [
        model.CodeRegion(m.start(), m.end(), False) for m in _CODE_SPAN.finditer(without_blocks)
    ]
    return sorted([*blocks, *spans])


def unclosed_string(text: str) -> int | None:
    return None


def marker_pattern() -> re.Pattern[str]:
    return _MARKER


def marker_carrier(text: str, match: re.Match[str], body_end: int) -> tuple[int, int] | None:
    """An inline marker carries only itself; one spelled for its own line (`]:`) carries
    the line and its line ending."""
    if match.group("own_line"):
        return lines.line_carrier(text, match, body_end)
    return match.start(), match.end()


def point_end(text: str, start: int, body_end: int) -> int:
    """A point anchor is a position."""
    return start


def find_section(
    text: str,
) -> tuple[model.Section | None, list[records.RecordLine], list[model.ParseError]]:
    """The section is the last header outside code. We mask code only in the text before
    a header, so a backtick inside a record can't pair with one in the body."""
    header = next(
        (
            h
            for h in reversed(list(_SECTION.finditer(text)))
            if _SECTION.match(
                lines.masked(text[: h.end()], code_regions(text[: h.end()])), h.start()
            )
        ),
        None,
    )
    if header is None:
        return None, [], []

    errors: list[model.ParseError] = []
    closing = text.find(_SECTION_END, header.end())
    if closing == -1:
        errors.append(_section_error(header.start(), "the threads section has no closing -->"))
        records_end = end = len(text)
    else:
        records_end = closing
        end = closing + len(_SECTION_END)
        for line_ending in ("\r\n", "\n"):
            if text.startswith(line_ending, end):
                end += len(line_ending)
                break
        if text[end:].strip():
            errors.append(_section_error(end, "text follows the threads section"))

    record_lines = [
        records.RecordLine(offset, line.strip())
        for offset, line in lines.yield_physical_lines(text, header.end() + 1, records_end)
        if line.strip()
    ]
    section = model.Section(
        start=lines.section_start(text, header.start()),
        insert_at=records_end,
        end=end,
        closed=closing != -1,
    )
    return section, record_lines, errors


def encode_record(json_line: str, newline: str) -> str:
    """We escape `>`, so a body can't close the section's HTML comment."""
    return json_line.replace(">", "\\u003e") + newline


def new_section(record_line: str, newline: str) -> str:
    return f"{newline}<!-- [lma:{model.SECTION_NAME}]{newline}{record_line}-->{newline}"


def place_anchor(
    text: str, start: int, end: int, doc: model.Document, comment_id: str
) -> list[model.Edit]:
    """Markers sit inline beside the selected text, trimmed of whitespace at its ends, after
    the line's block syntax (see `_opening_inline`). Around a fenced block, each marker
    takes a line of its own, spelled for its own line, so the fence still starts its line,
    and so does one that lands on a line holding only other markers, which an inline marker
    there would change. Whatever the rules place, the document must render as it did, or
    the comment is refused (`_check_rendering`)."""
    body_end = doc.section.start if doc.section else len(text)
    placed = _placed(text, start, end, doc, comment_id)
    _check_rendering(text[:body_end], [e for e in placed if e.start <= body_end])
    return placed


def _placed(
    text: str, start: int, end: int, doc: model.Document, comment_id: str
) -> list[model.Edit]:
    body_end = doc.section.start if doc.section else len(text)
    regions = code_regions(text[:body_end])
    existing, newline = doc.markers, doc.newline
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    _refuse_where_no_marker_fits(text, start, max(start, end - 1), regions, _delimiter_rows(text))
    if start == end:
        return [_point(text, start, regions, existing, newline, comment_id)]
    start, end, start_region, end_region = _grown(start, end, regions)
    start, end = _out_of_markers(start, existing), _out_of_markers(end, existing)
    if not end_region:
        end = _closing_spot(text, end)

    opening_line = f"<!-- [lma:{comment_id}]: -->{newline}"
    if start_region and start_region.block:
        opening = model.Edit(start, start, _indent_of(text, start) + opening_line)
    elif _is_marker_only_line(text, start):
        line_start = text.rfind("\n", 0, start) + 1
        opening = model.Edit(line_start, line_start, opening_line)
    else:
        opening = _opening_inline(text, start, comment_id)

    closing_line = f"<!-- [/lma:{comment_id}]: -->"
    if _RULE.match(_line_at(text, end)):
        # trailing text would make the rule a paragraph or the underline part of one
        after = text.find("\n", end)
        if after == -1:
            return [opening, model.Edit(len(text), len(text), f"{newline}{closing_line}")]
        return [opening, model.Edit(after + 1, after + 1, f"{closing_line}{newline}")]
    if end_region and end_region.block:
        after_fence = text.find("\n", end)
        if after_fence == -1:
            return [opening, model.Edit(end, end, f"{newline}{closing_line}")]
        indent = _indent_of(text, text.rfind("\n", 0, after_fence) + 1)
        return [
            opening,
            model.Edit(after_fence + 1, after_fence + 1, f"{indent}{closing_line}{newline}"),
        ]
    if _is_marker_only_line(text, end):
        line_start = text.rfind("\n", 0, end) + 1
        return [opening, model.Edit(line_start, line_start, f"{closing_line}{newline}")]
    return [opening, model.Edit(end, end, f"<!-- [/lma:{comment_id}] -->")]


def _section_error(offset: int, message: str) -> model.ParseError:
    return model.ParseError(offset, message, "section")


def _fences(text: str) -> list[model.CodeRegion]:
    """Fenced code blocks, at any block-quote depth. A fence closes on a line at the same
    depth with a run of its character at least as long; inside a block quote it also
    ends where the quote does, on the first line with fewer `>`. One that never closes
    runs to the end of the text."""
    regions: list[model.CodeRegion] = []
    open_fence: tuple[int, int, str] | None = None  # (start, depth, fence)
    offset = 0
    for line in text.split("\n"):
        prefix = _QUOTE_PREFIX.match(line)
        depth = prefix.group(0).count(">") if prefix else 0
        rest = line[prefix.end() if prefix else 0 :]
        if depth and rest.startswith(" "):
            rest = rest[1:]  # the one space a block quote marker may take
        opener = _FENCE_OPENER.match(rest)
        if opener and opener.group("char") == "`" and "`" in rest[opener.end() :]:
            opener = None  # a backtick fence's info string has no backticks: a code span
        if open_fence is not None:
            start, fence_depth, fence = open_fence
            if depth < fence_depth:
                regions.append(model.CodeRegion(start, offset - 1, True))
                open_fence = None  # and this line may open a fence of its own, below
            elif (
                depth == fence_depth
                and opener
                and opener.group("fence").startswith(fence)
                and not rest[opener.end() :].strip()
            ):
                regions.append(model.CodeRegion(start, offset + len(line), True))
                open_fence = None
                offset += len(line) + 1
                continue
        if open_fence is None and opener:
            open_fence = (offset, depth, opener.group("fence"))
        offset += len(line) + 1
    if open_fence is not None:
        regions.append(model.CodeRegion(open_fence[0], len(text), True))
    return regions


def _indented_code(text: str) -> list[model.CodeRegion]:
    """Indented code blocks: lines indented four spaces or a tab, after a blank line or
    another such line. Inside a list, an indented line continues the item instead, so we
    leave lines alone when the last line that isn't indented started a list item."""
    regions: list[model.CodeRegion] = []
    offset = 0
    previous_blank = True
    in_code = False
    in_list = False
    for line in text.split("\n"):
        blank = bool(_BLANK.fullmatch(line))
        indented = bool(_INDENTED.match(line)) and not blank
        if not blank and not indented:
            in_list = bool(_LIST_ITEM.match(line))
        in_code = indented and not in_list and (in_code or previous_blank)
        if in_code:
            regions.append(model.CodeRegion(offset, offset + len(line), True))
        elif not blank:
            in_code = False
        previous_blank = blank
        offset += len(line) + 1
    return regions


def _grown(
    start: int, end: int, regions: list[model.CodeRegion]
) -> tuple[int, int, model.CodeRegion | None, model.CodeRegion | None]:
    """`start` and `end` moved out of any region they fall inside, and those regions. A
    block region's own edges count as inside, so a marker never touches a fence."""
    start_region = next(
        (r for r in regions if r.start < start < r.end or (r.block and start == r.start)), None
    )
    end_region = next(
        (r for r in regions if r.start < end < r.end or (r.block and end == r.end)), None
    )
    return (
        start_region.start if start_region else start,
        end_region.end if end_region else end,
        start_region,
        end_region,
    )


def _delimiter_rows(text: str) -> frozenset[int]:
    """The line numbers of the tables' delimiter rows, by a CommonMark parser with tables:
    a line shaped like one is a delimiter row only when it really makes a table."""
    if "|" not in text:
        return frozenset()
    from markdown_it import MarkdownIt

    tokens = MarkdownIt("commonmark").enable("table").parse(text)
    return frozenset(t.map[0] + 1 for t in tokens if t.type == "table_open" and t.map)


def _refuse_where_no_marker_fits(
    text: str,
    first: int,
    last: int,
    regions: list[model.CodeRegion],
    delimiter_rows: frozenset[int],
) -> None:
    """Refuse a comment no marker can be invisible in: in YAML frontmatter, which has no
    HTML comments, so a marker would change its fields; on a table's delimiter row, which
    any text stops being one; on a thematic break or a setext heading's underline, which
    hold no text and any text changes; or on a heading with no text."""
    frontmatter = _FRONTMATTER.match(text)
    if frontmatter and first < frontmatter.end():
        raise ValueError("a comment can't go in a file's frontmatter: it would change its fields")
    for position in {first, last}:
        if any(r.block and r.start <= position <= r.end for r in regions):
            continue  # a marker goes outside the code, whatever its lines look like
        line = _line_at(text, position)
        rest = line[_CONTAINERS.match(line).end() :]
        if text.count("\n", 0, position) in delimiter_rows:
            raise ValueError("a table's delimiter row can't hold a comment; select a row or a cell")
        if position == first and _RULE.match(rest):
            # a closing marker can go on a line of its own after one; an opening one can't
            raise ValueError("a comment can't start on a rule or a heading's underline")
        heading = _HEADING.match(rest)
        if heading and not _CLOSING_HASHES.sub("", " " + rest[heading.end() :]).strip():
            raise ValueError("a heading with no text can't hold a comment")


# elements whose content a browser reads as text, where `<!--` is not a comment
_RAW_TEXT_ELEMENTS: ty.Final = frozenset(
    {"textarea", "title", "script", "style", "xmp", "iframe", "noembed", "noframes", "plaintext"}
)


class _Shown(html.parser.HTMLParser):
    """What a reader sees of some HTML: its tags with their attributes, and its text, with
    comment nodes and empty `<wbr>`s left out. Parsing, not pattern matching, so a marker
    that landed inside a tag's attribute shows up as a changed attribute."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[tuple[str, ...]] = []
        # the open element whose content a browser reads as text, to its own end tag
        self.raw_text: str | None = None

    # Some Python versions' parsers report tags and comments inside a textarea or title as
    # tags and comments; a browser reads everything up to that element's own end tag as
    # text (all of the rest, for plaintext), so we decide it ourselves.

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.raw_text:
            self.handle_data(self.get_starttag_text() or f"<{tag}>")
            return
        if tag in _RAW_TEXT_ELEMENTS:
            self.raw_text = tag
        if tag != "wbr" or attrs:  # only the bare `<wbr>` the workaround writes
            self.parts.append(("start", tag, repr(attrs)))

    def handle_endtag(self, tag: str) -> None:
        if self.raw_text and (tag != self.raw_text or tag == "plaintext"):
            self.handle_data(f"</{tag}>")
            return
        self.raw_text = None
        self.parts.append(("end", tag))

    def handle_comment(self, data: str) -> None:
        if self.raw_text:
            self.handle_data(f"<!--{data}-->")

    def handle_data(self, data: str) -> None:
        if self.parts and self.parts[-1][0] == "text":
            self.parts[-1] = ("text", self.parts[-1][1] + data)
        else:
            self.parts.append(("text", data))


def _shown(rendered: str) -> list[tuple[str, ...]]:
    parser = _Shown()
    parser.feed(rendered)
    parser.close()
    # a comment on a line of its own leaves its line break behind as text; whitespace
    # between blocks never shows, so it doesn't count
    return [p for p in parser.parts if p[0] != "text" or p[1].strip()]


def _check_rendering(body: str, placed: list[model.Edit]) -> None:
    """Refuse markers that change how the document renders: render it with a CommonMark
    parser (with tables, as GitHub has) before and after, and compare what a reader sees
    of each (`_Shown`). The placement rules above should
    never trip this; it catches what they don't foresee."""
    from markdown_it import MarkdownIt

    renderer = MarkdownIt("commonmark").enable("table")
    after = body
    for edit in sorted(placed, key=lambda e: e.start, reverse=True):
        after = after[: edit.start] + edit.text + after[edit.end :]

    if _shown(renderer.render(after)) != _shown(renderer.render(body)):
        raise ValueError("a comment here would change how the document renders")


def _point(
    text: str,
    position: int,
    regions: list[model.CodeRegion],
    existing: tuple[model.Marker, ...],
    newline: str,
    comment_id: str,
) -> model.Edit:
    """A point at or inside a fenced block goes on its own line before the fence, and one
    inside a code span goes before the span. A point on a line with no text but markers
    takes a line of its own; anywhere else it sits inline, outside any marker."""
    own_line = f"<!-- [lma:{comment_id}]: -->{newline}"
    block = next((r for r in regions if r.block and r.start <= position <= r.end), None)
    if block is not None:
        return model.Edit(block.start, block.start, _indent_of(text, block.start) + own_line)
    span = next((r for r in regions if r.start < position < r.end), None)
    if span is not None:
        return _opening_inline(text, span.start, comment_id)

    if _is_marker_only_line(text, position):
        line_start = text.rfind("\n", 0, position) + 1
        return model.Edit(line_start, line_start, own_line)
    position = _out_of_markers(position, existing)
    return _opening_inline(text, position, comment_id)


def _content_start(text: str, line_start: int, line_end: int) -> tuple[int, bool]:
    """Where a line's own text starts, after its block quote and list markers, a heading's
    `#`s, a table row's leading `|`, and indentation; and whether a marker can go there,
    inside the heading or the row's first cell, rather than on a line before."""
    content = _CONTAINERS.match(text, line_start, line_end).end()
    if inside := _HEADING.match(text, content, line_end) or _TABLE_ROW.match(
        text, content, line_end
    ):
        return inside.end(), True
    while content < line_end and text[content] in " \t":
        content += 1
    return content, False


def _closing_spot(text: str, end: int) -> int:
    """Where a closing marker can go for a selection ending at *end*: a selection that ends
    in a line's block markers (only the `-` or the `#`) means the line, so it ends with the
    line's text; and a selection that ends with a line's trailing backslash ends before it,
    so the backslash still breaks the line rather than escaping the marker."""
    line_start = text.rfind("\n", 0, end - 1) + 1 if end else 0
    line_end = text.find("\n", line_start)
    line_end = len(text) if line_end == -1 else line_end
    content, _ = _content_start(text, line_start, line_end)
    if end <= content and text[content:line_end].strip():
        end = line_start + len(text[line_start:line_end].rstrip(" \t\r"))
    rest_of_line = text[end:line_end]
    is_table_row = _TABLE_ROW.match(text, _CONTAINERS.match(text, line_start, line_end).end())
    if is_table_row and not rest_of_line.strip(" \t\r") and text[:end].endswith("|"):
        # inside the last cell: text after a row's last `|` can stop a header being one
        end = len(text[: end - 1].rstrip(" \t"))
    heading = _HEADING.match(text, _CONTAINERS.match(text, line_start, line_end).end(), line_end)
    if heading and not rest_of_line.strip(" \t\r"):
        # before a heading's closing `#`s, which are only its closing sequence while they end it
        closing_hashes = _CLOSING_HASHES.search(text, heading.end(), end)
        if closing_hashes:
            end = closing_hashes.start()
    if end and text[end - 1] == "\\" and not rest_of_line.strip(" \t\r"):
        end -= 1
    return end


def _indent_of(text: str, line_start: int) -> str:
    """The spaces and tabs a fence line starts with: a marker on a line of its own beside a
    fenced block takes the fence's, so a fence inside a list item stays inside it. Beside
    an indented code block, none: indented like the code, the marker would be code."""
    line = _line_at(text, line_start)
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    return indent if _FENCE_OPENER.match(line.lstrip(" \t")) else ""


def _line_at(text: str, position: int) -> str:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    return text[line_start : len(text) if line_end == -1 else line_end]


def _opening_inline(text: str, position: int, comment_id: str) -> model.Edit:
    """An opening marker at *position*, after the line's block syntax when the comment
    starts there: after a heading's `#`s and inside a table row's first cell as it is, and
    after a list item's or block quote's markers, or at a paragraph line's start, with the
    `<wbr>` workaround in front (see `_WBR`), so the line's text doesn't start with `<!--`."""
    marker = f"<!-- [lma:{comment_id}] -->"
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line_end = len(text) if line_end == -1 else line_end
    content, inline_already = _content_start(text, line_start, line_end)
    if position > content:
        return model.Edit(position, position, marker)
    if inline_already:
        return model.Edit(content, content, marker)
    return model.Edit(content, content, f"{_WBR}<!-- [lma:{comment_id}] wbr -->")


def _out_of_markers(position: int, existing: tuple[model.Marker, ...]) -> int:
    """`position`, moved to the end of any marker it falls inside."""
    inside = next((m for m in existing if m.carrier[0] < position < m.carrier[1]), None)
    return inside.carrier[1] if inside else position


def _is_marker_only_line(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    return not _MARKER.sub("", line).strip()
