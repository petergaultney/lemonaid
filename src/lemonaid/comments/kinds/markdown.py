"""Markdown files: markers are HTML comments, inline or on lines of their own, and the
threads section is one HTML comment at the end. A CommonMark parser with tables
(markdown-it-py) tells us the document's structure: its fenced and indented code blocks,
and where each line's own text starts and ends after its block syntax (`_Structure`)."""

import functools
import html.parser
import re
import typing as ty

from .. import lines, model, records

if ty.TYPE_CHECKING:
    from markdown_it import MarkdownIt

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
_CODE_SPAN: ty.Final = re.compile(r"(`+)(?!`).*?(?<!`)\1(?!`)", re.S)
# a leading byte order mark, then `---` to the next `---` or `...` line, which may be the
# next: YAML, which CommonMark doesn't know, so the parser can't find it for us
_FRONTMATTER: ty.Final = re.compile(
    r"\ufeff?---[ \t]*\r?\n(?:.*?\n)??(?:---|\.\.\.)[ \t]*(?:\r?\n|$)", re.S
)
# the parser reads a CR on its own as a line ending; only `\n` ends one here (`lines`)
_LONE_CR: ty.Final = re.compile(r"\r(?!\n)")


def code_regions(text: str) -> list[model.CodeRegion]:
    return _code_regions(text, _structure(text))


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
    candidates = list(_SECTION.finditer(text))
    if not candidates:
        return None, [], []
    # A header line starts with `<!--` at the margin, which ends any list or quote before
    # it, so the text after it can't change whether it is in a code block: one parse of
    # the whole text serves every candidate.
    blocks = _structure(text).blocks
    header = next(
        (
            h
            for h in reversed(candidates)
            if _SECTION.match(_without_code_before(text, h.end(), blocks), h.start())
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
    structure = _structure(text[:body_end])
    regions = _code_regions(text[:body_end], structure)
    existing, newline = doc.markers, doc.newline
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    _refuse_where_no_marker_fits(text, start, max(start, end - 1), regions, structure)
    if start == end:
        return [_point(text, start, regions, structure, existing, newline, comment_id)]
    start, end, start_region, end_region = _grown(start, end, regions)
    start, end = _out_of_markers(start, existing), _out_of_markers(end, existing)
    if not end_region:
        end = _closing_spot(text, end, structure)

    opening_line = f"<!-- [lma:{comment_id}]: -->{newline}"
    if start_region and start_region.block:
        opening = model.Edit(start, start, _indent_of(text, start, structure) + opening_line)
    elif _is_marker_only_line(text, start):
        line_start = text.rfind("\n", 0, start) + 1
        opening = model.Edit(line_start, line_start, opening_line)
    else:
        opening = _opening_inline(text, start, comment_id, structure)

    closing_line = f"<!-- [/lma:{comment_id}]: -->"
    if text.count("\n", 0, end) in structure.textless:
        # trailing text would make the rule a paragraph or the underline part of one
        after = text.find("\n", end)
        if after == -1:
            return [opening, model.Edit(len(text), len(text), f"{newline}{closing_line}")]
        return [opening, model.Edit(after + 1, after + 1, f"{closing_line}{newline}")]
    if end_region and end_region.block:
        after_fence = text.find("\n", end)
        if after_fence == -1:
            return [opening, model.Edit(end, end, f"{newline}{closing_line}")]
        indent = _indent_of(text, text.rfind("\n", 0, after_fence) + 1, structure)
        return [
            opening,
            model.Edit(after_fence + 1, after_fence + 1, f"{indent}{closing_line}{newline}"),
        ]
    if _is_marker_only_line(text, end):
        line_start = text.rfind("\n", 0, end) + 1
        return [opening, model.Edit(line_start, line_start, f"{closing_line}{newline}")]
    return [opening, model.Edit(end, end, f"<!-- [/lma:{comment_id}] -->")]


def _without_code_before(text: str, end: int, blocks: list[model.CodeRegion]) -> str:
    """`text[:end]` with its code masked: code blocks as the whole text has them, cut at
    *end*, and code spans found in the masked prefix alone."""
    prefix = text[:end]
    without_blocks = lines.masked(
        prefix, [b._replace(end=min(b.end, end)) for b in blocks if b.start < end]
    )
    return lines.masked(
        without_blocks,
        [model.CodeRegion(m.start(), m.end(), False) for m in _CODE_SPAN.finditer(without_blocks)],
    )


def _section_error(offset: int, message: str) -> model.ParseError:
    return model.ParseError(offset, message, "section")


class _Text(ty.NamedTuple):
    """A line's own text, after its block syntax, as `[start, end)` in the document."""

    start: int
    end: int
    # an ATX heading's, or a table row's after its leading `|`: there a marker at the
    # start needs no `<wbr>`
    inline: bool


class _Structure(ty.NamedTuple):
    """What a CommonMark parser with tables says about a document, by line number. A line
    that has no `text` (a blank line, a link reference definition, raw HTML, a fence)
    gets its markers where the selection puts them, and the render check decides."""

    text: dict[int, _Text]
    blocks: list[model.CodeRegion]
    fence_edges: frozenset[int]  # a fenced block's first and last lines
    textless: frozenset[int]  # thematic breaks and setext headings' underlines
    delimiter_rows: frozenset[int]
    empty_headings: frozenset[int]


@functools.cache
def _parser(*, blocks_only: bool = False) -> "MarkdownIt":
    """CommonMark with tables. *blocks_only* leaves inline tokens unparsed, which is all
    `_structure` needs and several times faster; rendering needs them parsed."""
    from markdown_it import MarkdownIt  # here, so a command that reads no Markdown skips it

    parser = MarkdownIt("commonmark").enable("table")
    if blocks_only:
        parser.core.ruler.disable(["inline", "text_join"])
    return parser


def _structure(text: str) -> _Structure:
    """The parser gives each block its lines, and each inline token its text with the
    block syntax taken off, but no columns: a line's text is where that content sits in
    the line (`_located`)."""
    tokens = _parser(blocks_only=True).parse(_LONE_CR.sub(" ", text))
    line_starts = [0, *(m.end() for m in re.finditer("\n", text))]

    def line_span(number: int) -> tuple[int, int]:
        end = line_starts[number + 1] - 1 if number + 1 < len(line_starts) else len(text)
        return line_starts[number], end

    own_text: dict[int, _Text] = {}
    blocks: list[model.CodeRegion] = []
    fence_edges: set[int] = set()
    textless: set[int] = set()
    delimiter_rows: set[int] = set()
    empty_headings: set[int] = set()
    cells_by_line: dict[int, list[_Cell]] = {}
    for i, token in enumerate(tokens):
        if token.map is None:
            continue
        first, after = token.map
        if token.type in ("fence", "code_block"):
            blocks.append(model.CodeRegion(line_span(first)[0], line_span(after - 1)[1], True))
            if token.type == "fence":
                fence_edges |= {first, after - 1}
        elif token.type == "hr":
            textless.add(first)
        elif token.type == "heading_open" and token.markup in ("=", "-"):
            textless.add(after - 1)
        elif token.type == "table_open":
            delimiter_rows.add(first + 1)
        elif token.type == "inline" and tokens[i - 1].type in ("th_open", "td_open"):
            line_start, line_end = line_span(first)
            if first not in cells_by_line:
                cells_by_line[first] = _cells(text[line_start:line_end])
            cell = _next_cell(cells_by_line[first], token.content.strip(" \t"))
            if cell is None:
                continue
            start, end = line_start + cell[0], line_start + cell[1]
            if first in own_text:
                own_text[first] = own_text[first]._replace(end=end)
            else:
                # a row with no leading `|` starts with its first cell's text, like a paragraph
                after_a_pipe = text[line_start:start].rstrip(" \t").endswith("|")
                own_text[first] = _Text(start, end, after_a_pipe)
        elif token.type == "inline":
            opener = tokens[i - 1]
            atx_heading = opener.type == "heading_open" and opener.markup.startswith("#")
            if atx_heading and not token.content.strip():
                empty_headings.add(first)
            for number, content in zip(
                range(first, after), token.content.split("\n"), strict=False
            ):
                line_start, line_end = line_span(number)
                line = text[line_start:line_end]
                # an ATX heading's text starts right after its opening `#`s; any other
                # line's text is the end of the line
                found = (
                    _after(line, opener.markup, content)
                    if atx_heading
                    else _at_the_end(line, content)
                )
                if found is not None:
                    own_text[number] = _Text(
                        line_start + found[0], line_start + found[1], atx_heading
                    )
    return _Structure(
        own_text,
        blocks,
        frozenset(fence_edges),
        frozenset(textless),
        frozenset(delimiter_rows),
        frozenset(empty_headings),
    )


def _at_the_end(line: str, content: str) -> tuple[int, int] | None:
    core = content.strip(" \t")
    trimmed = line.rstrip(" \t\r")
    if not core or not trimmed.endswith(core):
        return None
    return len(trimmed) - len(core), len(trimmed)


def _after(line: str, opening: str, content: str) -> tuple[int, int] | None:
    """*content* where it first occurs after *opening*: the opening `#`s come after any
    block quote or list markers, which hold no `#`, and only spaces come between them and
    the text."""
    core = content.strip(" \t")
    after_opening = line.find(opening) + len(opening)
    start = line.find(core, after_opening) if core else -1
    return None if start == -1 else (start, start + len(core))


class _Cell(ty.NamedTuple):
    """A stretch of a table row between `|`s: `[start, end)` in the line without its
    surrounding spaces, and the text the parser gives a cell there."""

    start: int
    end: int
    text: str
    first: bool  # the row's first stretch, which also holds any block quote and list markers


def _cells(line: str) -> list[_Cell]:
    """*line* split as markdown-it splits a table row: a `|` after a backslash is text,
    and the backslash goes."""
    stretches: list[tuple[int, int]] = []
    stretch_start = 0
    escaped = False
    for position, char in enumerate(line):
        if char == "|" and not escaped:
            stretches.append((stretch_start, position))
            stretch_start = position + 1
        escaped = char == "\\"
    stretches.append((stretch_start, len(line.rstrip("\r"))))
    cells = []
    for start, end in stretches:
        raw = line[start:end]
        start += len(raw) - len(raw.lstrip(" \t"))
        end = max(start, end - (len(raw) - len(raw.rstrip(" \t"))))
        cells.append(_Cell(start, end, line[start:end].replace("\\|", "|"), not cells))
    return cells


def _next_cell(cells: list[_Cell], content: str) -> tuple[int, int] | None:
    """The first of *cells* that holds *content*, taken off the list, so the row's next
    cell is looked for after it. In a row with no leading `|`, the first stretch starts
    with the row's block quote and list markers (the parser took them off already), and
    the cell's text ends it."""
    if not content:
        return None
    for index, cell in enumerate(cells):
        markers = cell.text.removesuffix(content) if cell.text.endswith(content) else None
        if markers == "" or (cell.first and markers is not None):
            del cells[: index + 1]
            return cell.start + len(markers), cell.end
    return None


def _code_regions(text: str, structure: _Structure) -> list[model.CodeRegion]:
    """The parser's code blocks, then code spans in the text that is left."""
    without_blocks = lines.masked(text, structure.blocks)
    spans = [
        model.CodeRegion(m.start(), m.end(), False) for m in _CODE_SPAN.finditer(without_blocks)
    ]
    return sorted([*structure.blocks, *spans])


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


def _refuse_where_no_marker_fits(
    text: str, first: int, last: int, regions: list[model.CodeRegion], structure: _Structure
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
        line = text.count("\n", 0, position)
        if line in structure.delimiter_rows:
            raise ValueError("a table's delimiter row can't hold a comment; select a row or a cell")
        if position == first and line in structure.textless:
            # a closing marker can go on a line of its own after one; an opening one can't
            raise ValueError("a comment can't start on a rule or a heading's underline")
        if line in structure.empty_headings:
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
    renderer = _parser()
    after = body
    for edit in sorted(placed, key=lambda e: e.start, reverse=True):
        after = after[: edit.start] + edit.text + after[edit.end :]

    if _shown(renderer.render(after)) != _shown(renderer.render(body)):
        raise ValueError("a comment here would change how the document renders")


def _point(
    text: str,
    position: int,
    regions: list[model.CodeRegion],
    structure: _Structure,
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
        indent = _indent_of(text, block.start, structure)
        return model.Edit(block.start, block.start, indent + own_line)
    span = next((r for r in regions if r.start < position < r.end), None)
    if span is not None:
        return _opening_inline(text, span.start, comment_id, structure)

    if _is_marker_only_line(text, position):
        line_start = text.rfind("\n", 0, position) + 1
        return model.Edit(line_start, line_start, own_line)
    position = _out_of_markers(position, existing)
    return _opening_inline(text, position, comment_id, structure)


def _closing_spot(text: str, end: int, structure: _Structure) -> int:
    """Where a closing marker can go for a selection ending at *end*: at the end of its
    line's text when the selection ends outside it, in the line's block markers (only the
    `-` or the `#`, which means the line) or after it (a heading's closing `#`s, a table
    row's last `|`); and before a trailing backslash, so the backslash still breaks the
    line rather than escaping the marker."""
    own = structure.text.get(text.count("\n", 0, end - 1) if end else 0)
    if own is None:
        return end
    if end <= own.start or end > own.end:
        end = own.end
    if end == own.end and text[end - 1] == "\\":
        end -= 1
    return end


def _indent_of(text: str, line_start: int, structure: _Structure) -> str:
    """The spaces and tabs a fence line starts with: a marker on a line of its own beside a
    fenced block takes the fence's, so a fence inside a list item stays inside it. Beside
    an indented code block, none: indented like the code, the marker would be code."""
    if text.count("\n", 0, line_start) not in structure.fence_edges:
        return ""
    line_end = text.find("\n", line_start)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    return line[: len(line) - len(line.lstrip(" \t"))]


def _opening_inline(text: str, position: int, comment_id: str, structure: _Structure) -> model.Edit:
    """An opening marker at *position*, or at the start of its line's text when the
    comment starts at or before it: there as it is in an ATX heading or a table row's
    first cell, and with the `<wbr>` workaround in front (see `_WBR`) in a list item's,
    a block quote's or a paragraph's line, so the line's text doesn't start with `<!--`."""
    marker = f"<!-- [lma:{comment_id}] -->"
    own = structure.text.get(text.count("\n", 0, position))
    if own is None or position > own.start:
        return model.Edit(position, position, marker)
    if own.inline:
        return model.Edit(own.start, own.start, marker)
    return model.Edit(own.start, own.start, f"{_WBR}<!-- [lma:{comment_id}] wbr -->")


def _out_of_markers(position: int, existing: tuple[model.Marker, ...]) -> int:
    """`position`, moved to the end of any marker it falls inside."""
    inside = next((m for m in existing if m.carrier[0] < position < m.carrier[1]), None)
    return inside.carrier[1] if inside else position


def _is_marker_only_line(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    return not _MARKER.sub("", line).strip()
