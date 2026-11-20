"""Markdown files: markers are HTML comments, inline or on lines of their own, and the
threads section is one HTML comment at the end. We find code ourselves: fences at any
block-quote depth, indented code blocks outside lists, and code spans."""

import re
import typing as ty

from .. import lines, model, records

_MARKER: ty.Final = re.compile(
    r"<!--[ \t]*\[(?P<close>/)?lma:(?P<id>[A-Za-z][\w-]*)\](?P<own_line>:)?[ \t]*-->"
)
_SECTION: ty.Final = re.compile(r"^<!-- \[lma:threads\]\r?$", re.M)
_SECTION_END: ty.Final = "-->"
_QUOTE_PREFIX: ty.Final = re.compile(r"(?: {0,3}>)*")
_FENCE_OPENER: ty.Final = re.compile(r" {0,3}(?P<fence>(?P<char>[`~])(?P=char){2,})")
_BLANK: ty.Final = re.compile(r"[ \t\r]*")
_INDENTED: ty.Final = re.compile(r"(?: {4}|\t)")
_LIST_ITEM: ty.Final = re.compile(r" {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_CODE_SPAN: ty.Final = re.compile(r"(`+)(?!`).*?(?<!`)\1(?!`)", re.S)


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
    """Markers sit inline beside the selected text, trimmed of whitespace at its ends.
    Around a fenced block, each marker takes a line of its own, spelled for its own line,
    so the fence still starts its line, and so does one that lands on a line holding only
    other markers, which an inline marker there would change."""
    body_end = doc.section.start if doc.section else len(text)
    regions = code_regions(text[:body_end])
    existing, newline = doc.markers, doc.newline
    if start == end:
        return [_point(text, start, regions, existing, newline, comment_id)]

    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start == end:
        return [_point(text, start, regions, existing, newline, comment_id)]
    start, end, start_region, end_region = _grown(start, end, regions)
    start, end = _out_of_markers(start, existing), _out_of_markers(end, existing)

    opening_line = f"<!-- [lma:{comment_id}]: -->{newline}"
    if start_region and start_region.block:
        opening = model.Edit(start, start, opening_line)
    elif _is_marker_only_line(text, start):
        line_start = text.rfind("\n", 0, start) + 1
        opening = model.Edit(line_start, line_start, opening_line)
    else:
        opening = model.Edit(start, start, f"<!-- [lma:{comment_id}] -->")

    closing_line = f"<!-- [/lma:{comment_id}]: -->"
    if end_region and end_region.block:
        after_fence = text.find("\n", end)
        if after_fence == -1:
            return [opening, model.Edit(end, end, f"{newline}{closing_line}")]
        return [opening, model.Edit(after_fence + 1, after_fence + 1, f"{closing_line}{newline}")]
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
    inline = f"<!-- [lma:{comment_id}] -->"
    own_line = f"<!-- [lma:{comment_id}]: -->{newline}"
    block = next((r for r in regions if r.block and r.start <= position <= r.end), None)
    if block is not None:
        return model.Edit(block.start, block.start, own_line)
    span = next((r for r in regions if r.start < position < r.end), None)
    if span is not None:
        return model.Edit(span.start, span.start, inline)

    if _is_marker_only_line(text, position):
        line_start = text.rfind("\n", 0, position) + 1
        return model.Edit(line_start, line_start, own_line)
    position = _out_of_markers(position, existing)
    return model.Edit(position, position, inline)


def _out_of_markers(position: int, existing: tuple[model.Marker, ...]) -> int:
    """`position`, moved to the end of any marker it falls inside."""
    inside = next((m for m in existing if m.carrier[0] < position < m.carrier[1]), None)
    return inside.carrier[1] if inside else position


def _is_marker_only_line(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    return not _MARKER.sub("", line).strip()
