"""Python files: markers and the threads section are `#` comment lines, and Python's own
tokenizer says where strings and continued lines are."""

import io
import re
import tokenize
import typing as ty

from .. import lines, model, records

_MARKER: ty.Final = re.compile(
    r"^[ \t]*#[ \t]*\[(?P<close>/)?lma:(?P<id>[A-Za-z][\w-]*)\][ \t\r]*$", re.M
)
_SECTION: ty.Final = re.compile(r"^# \[lma:threads\]\r?$", re.M)
_SHEBANG: ty.Final = "#!"
_CODING: ty.Final = re.compile(r"[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
_STRING_STARTS: ty.Final = frozenset({"FSTRING_START", "TSTRING_START"})
_STRING_ENDS: ty.Final = frozenset({"FSTRING_END", "TSTRING_END"})
_LINE_ENDING_TOKENS: ty.Final = frozenset(
    {"NEWLINE", "NL", "COMMENT", "INDENT", "DEDENT", "ENCODING", "ENDMARKER"}
)


def code_regions(text: str) -> list[model.CodeRegion]:
    """Every string, and from a string that is never closed to the end of the text."""
    layout = _layout(text)
    unclosed = (
        [model.CodeRegion(layout.unclosed_string, len(text), True)]
        if layout.unclosed_string is not None
        else []
    )
    return [*layout.strings, *unclosed]


def unclosed_string(text: str) -> int | None:
    return _layout(text).unclosed_string


def marker_pattern() -> re.Pattern[str]:
    return _MARKER


def marker_carrier(text: str, match: re.Match[str], body_end: int) -> tuple[int, int] | None:
    """A marker carries its line and the line ending after it. The match must also be a
    marker in the original text: masking turns the end of a string into spaces, which
    the pattern would take for indentation, so a comment after a string's closing
    quotes is code, not a marker."""
    if not text[match.start() : match.end()].lstrip().startswith("#"):
        return None
    return lines.line_carrier(text, match, body_end)


def point_end(text: str, start: int, body_end: int) -> int:
    """A point anchor covers the line below its marker."""
    return lines.line_end(text, start, body_end)


def find_section(
    text: str,
) -> tuple[model.Section | None, list[records.RecordLine], list[model.ParseError]]:
    """The section is the last header outside a string with only comments after it."""
    strings = _layout(text).strings
    headers = [
        h for h in _SECTION.finditer(text) if not any(s.start <= h.start() < s.end for s in strings)
    ]
    if not headers:
        return None, [], []
    header = headers[-1]

    record_lines: list[records.RecordLine] = []
    for offset, line in lines.yield_physical_lines(text, header.end() + 1, len(text)):
        content = line.strip()
        if not content:
            continue
        if not content.startswith("#"):
            return None, [], []
        if payload := content[1:].strip():
            record_lines.append(records.RecordLine(offset, payload))

    section = model.Section(
        start=lines.section_start(text, header.start()),
        insert_at=len(text),
        end=len(text),
        closed=True,
    )
    return section, record_lines, []


def encode_record(json_line: str, newline: str) -> str:
    return f"# {json_line}{newline}"


def new_section(record_line: str, newline: str) -> str:
    return f"{newline}# [lma:{model.SECTION_NAME}]{newline}{record_line}"


def place_anchor(
    text: str, start: int, end: int, doc: model.Document, comment_id: str
) -> list[model.Edit]:
    """Markers go on lines of their own around whole lines. When a marker's line would
    land inside a string or after a backslash continuation, the range grows a line at a
    time until it doesn't."""
    if doc.unclosed_string is not None:
        raise ValueError("a string in this file is never closed; close it before commenting")
    body_end = doc.section.start if doc.section else len(text)
    newline = doc.newline
    unsafe = _unsafe_line_starts(text[:body_end])

    first_line = text.rfind("\n", 0, start) + 1
    while first_line in unsafe:
        first_line = text.rfind("\n", 0, first_line - 1) + 1
    if first_line < _protected_prefix_end(text):
        raise ValueError("a marker can't go above the shebang or encoding line")

    covers_whole_last_line = end > start and text[end - 1] == "\n"
    last_end = max(end - 1 if covers_whole_last_line else end, first_line)
    found = text.find("\n", last_end, body_end)
    while start != end and found != -1 and found + 1 in unsafe:
        found = text.find("\n", found + 1, body_end)
    last_line_end = body_end if found == -1 else found

    indent = _least_indent(text[first_line:last_line_end])
    opening = model.Edit(first_line, first_line, f"{indent}# [lma:{comment_id}]{newline}")
    if start == end:
        return [opening]

    closing_marker = f"{indent}# [/lma:{comment_id}]"
    if found == -1:
        return [opening, model.Edit(body_end, body_end, f"{newline}{closing_marker}")]
    return [opening, model.Edit(found + 1, found + 1, f"{closing_marker}{newline}")]


class _Layout(ty.NamedTuple):
    strings: list[model.CodeRegion]
    unclosed_string: int | None
    continued_line_starts: frozenset[int]
    line_starts: list[int]


def _layout(text: str) -> _Layout:
    """What the tokenizer says about `text`'s lines. A file that doesn't tokenize (one
    being edited) gives what was found before the error, and a string left open at the
    end is reported by where it starts."""
    line_starts = [0]
    for line in text.split("\n")[:-1]:
        line_starts.append(line_starts[-1] + len(line) + 1)

    def offset(row_col: tuple[int, int]) -> int:
        row, col = row_col
        return line_starts[row - 1] + col if row - 1 < len(line_starts) else len(text)

    strings: list[model.CodeRegion] = []
    open_starts: list[tuple[int, int]] = []
    continued: set[int] = set()
    unclosed: int | None = None
    previous_end_row: int | None = None
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            name = tokenize.tok_name[token.type]
            if previous_end_row is not None and token.start[0] > previous_end_row:
                # Python 3.11's tokenizer also ends a line at a bare CR, which `line_starts`
                # doesn't count, so its rows can run past the list.
                rows = range(previous_end_row, min(token.start[0], len(line_starts)))
                continued |= {line_starts[row] for row in rows}
            previous_end_row = None if name in _LINE_ENDING_TOKENS else token.end[0]
            if name == "STRING":
                strings.append(
                    model.CodeRegion(
                        offset(token.start), offset(token.end), token.start[0] != token.end[0]
                    )
                )
            elif name in _STRING_STARTS:
                open_starts.append(token.start)
            elif name in _STRING_ENDS and open_starts:
                start = open_starts.pop()
                if not open_starts:
                    strings.append(
                        model.CodeRegion(offset(start), offset(token.end), start[0] != token.end[0])
                    )
    except tokenize.TokenError as e:
        if "string" in str(e.args[0]) and len(e.args) > 1:
            unclosed = offset(e.args[1])
            while unclosed > 0 and text[unclosed - 1] in "\"'":
                unclosed -= 1  # some versions point inside the opening quotes
        elif open_starts:
            unclosed = offset(open_starts[0])
    except SyntaxError:
        pass
    return _Layout(strings, unclosed, frozenset(continued), line_starts)


def _unsafe_line_starts(text: str) -> frozenset[int]:
    """Line starts where inserting a line would change the code: inside a string that
    spans lines, after a backslash continuation, and anywhere after a string the file
    never closes."""
    layout = _layout(text)
    strings = code_regions(text)
    inside_strings = {
        line_start
        for line_start in layout.line_starts
        if any(r.start < line_start < r.end for r in strings)
    }
    return frozenset(inside_strings | layout.continued_line_starts)


def _protected_prefix_end(text: str) -> int:
    """The end of the leading lines Python reads by position: a shebang on line 1 and an
    encoding declaration on line 1 or 2."""
    protected = 0
    offset = 0
    for index, line in enumerate(text.split("\n")[:2]):
        offset += len(line) + 1
        if (index == 0 and line.startswith(_SHEBANG)) or _CODING.match(line):
            protected = min(offset, len(text))
    return protected


def _least_indent(text: str) -> str:
    indents = [
        line[: len(line) - len(line.lstrip(" \t"))] for line in text.split("\n") if line.strip()
    ]
    return min(indents, key=len, default="")
