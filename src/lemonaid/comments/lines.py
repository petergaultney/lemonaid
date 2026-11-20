"""Offsets and lines in a file's text, shared by the kinds.

Only `\\n` ends a line here, as it does for Python's tokenizer, so a U+2028 or U+0085 in
the text doesn't split a line.
"""

import re
from collections import abc

from . import model


def masked(text: str, regions: abc.Iterable[model.CodeRegion]) -> str:
    """`text` with each region blanked to spaces, newlines kept, so offsets don't move."""
    chars = list(text)
    for region in regions:
        for i in range(region.start, region.end):
            if chars[i] not in "\r\n":
                chars[i] = " "
    return "".join(chars)


def yield_physical_lines(text: str, start: int, end: int) -> abc.Iterator[tuple[int, str]]:
    """(offset, line without its line ending) for each line of `text[start:end]`."""
    offset = start
    for line in text[start:end].split("\n"):
        yield offset, line.removesuffix("\r")
        offset += len(line) + 1


def section_start(text: str, header_start: int) -> int:
    """Where the threads section starts: the one line ending before its header, which
    the writer always puts there, belongs to the section."""
    for line_ending in ("\r\n", "\n"):
        if text[:header_start].endswith(line_ending):
            return header_start - len(line_ending)
    return header_start


def line_carrier(text: str, m: re.Match[str], body_end: int) -> tuple[int, int]:
    """A marker alone on its line carries the line and the line ending after it; on the
    body's last line, which has none, just the line. One with other text on its line
    carries only itself."""
    line_start = text.rfind("\n", 0, m.start()) + 1
    newline = text.find("\n", m.end(), body_end)
    line_end = body_end if newline == -1 else newline
    if text[line_start : m.start()].strip() or text[m.end() : line_end].strip():
        return m.start(), m.end()
    return line_start, body_end if newline == -1 else newline + 1


def line_end(text: str, start: int, limit: int) -> int:
    """The end of the line at `start`, before its line ending."""
    newline = text.find("\n", start, limit)
    end = limit if newline == -1 else newline
    return end - 1 if text[start:end].endswith("\r") else end
